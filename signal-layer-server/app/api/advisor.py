"""策略建议接口。

分析是异步任务：POST 建 run 立即返回，前端轮询进度；
结果包含结论、画像、候选明细与淘汰原因，可按需把建议落成真实策略模板。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_advisor_service
from app.api.security import require_permission
from app.db import get_session
from app.engine.advisor.scoring import Constraints
from app.engine.advisor.types import CandidateResult, TradeStats
from app.models.advisor import AdvisorCandidate, AdvisorRecommendation, AdvisorRun
from app.models.auth import User
from app.models.template import Template
from app.schemas.advisor import (
    AdvisorCandidateItem,
    AdvisorRecommendationItem,
    AdvisorRunCreate,
    AdvisorRunResponse,
    AdvisorRunSummary,
    AdvisorTemplateResponse,
    AdvisorTemplateSave,
    AdvisorTradeStats,
)
from app.services.advisor_service import (
    ENGINE_VERSION,
    AdvisorService,
    candidate_from_payload,
    candidate_payload,
)
from app.services.auth_service import permission_codes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/advisor", tags=["advisor"])

_ACTIVE_TASKS: set[asyncio.Task] = set()


def _stats_payload(stats: TradeStats | None) -> AdvisorTradeStats | None:
    if stats is None:
        return None
    return AdvisorTradeStats(
        trades=stats.trades,
        win_rate=round(stats.win_rate, 2),
        total_return=round(stats.total_return, 2),
        max_drawdown=round(stats.max_drawdown, 2),
        profit_factor=round(stats.profit_factor, 2),
        frequency=round(stats.frequency, 4),
        expectancy=round(stats.expectancy, 4),
    )


def _constraints_of(payload) -> Constraints:
    defaults = Constraints()
    if payload is None:
        return defaults
    return Constraints(
        min_trades=payload.min_trades if payload.min_trades is not None else defaults.min_trades,
        min_win_rate=payload.min_win_rate if payload.min_win_rate is not None else defaults.min_win_rate,
        min_frequency=payload.min_frequency if payload.min_frequency is not None else defaults.min_frequency,
        max_frequency=payload.max_frequency if payload.max_frequency is not None else defaults.max_frequency,
        min_out_of_sample_return=(
            payload.min_out_of_sample_return
            if payload.min_out_of_sample_return is not None
            else defaults.min_out_of_sample_return
        ),
        min_out_of_sample_trades=(
            payload.min_out_of_sample_trades
            if payload.min_out_of_sample_trades is not None
            else defaults.min_out_of_sample_trades
        ),
    )


async def _run_analysis(run_id: int, body: AdvisorRunCreate) -> None:
    """后台执行分析并落库。使用独立会话，异常写回 run.error。"""
    service = get_advisor_service()
    async for session in get_session():
        try:
            run = await session.get(AdvisorRun, run_id)
            if run is None:
                return

            async def on_progress(stage: str, percent: int) -> None:
                run.stage = stage
                run.progress_percent = percent
                await session.commit()

            run.status = "running"
            run.started_at = datetime.now()
            await session.commit()

            result = await service.analyze(
                body.symbol,
                constraints=_constraints_of(body.constraints),
                selection_ratio=body.selection_ratio,
                segments=body.segments,
                budget=body.budget,
                limit=body.kline_limit,
                on_progress=on_progress,
            )
            await _persist_result(session, run, result)
        except Exception as error:  # 失败也要让前端看到原因
            logger.exception("advisor run %s failed", run_id)
            async for inner in get_session():
                failed = await inner.get(AdvisorRun, run_id)
                if failed is not None:
                    failed.status = "failed"
                    failed.error = str(error)[:500]
                    failed.progress_percent = 100
                    failed.finished_at = datetime.now()
                    await inner.commit()
            return
        return


async def _persist_result(session: AsyncSession, run: AdvisorRun, result: dict) -> None:
    await session.execute(delete(AdvisorCandidate).where(AdvisorCandidate.run_id == run.id))

    results: list[CandidateResult] = result.get("results") or []
    for rank, item in enumerate(results):
        session.add(AdvisorCandidate(
            run_id=run.id,
            rank=rank,
            family=item.candidate.family,
            primary_level=item.candidate.primary_level,
            entry_level=item.candidate.entry_level,
            description=item.candidate.describe()[:400],
            passed=True,
            plateau_stable=item.plateau_stable,
            score=round(item.score, 4),
            in_sample=_stats_payload(item.in_sample).model_dump() if item.in_sample else None,
            out_of_sample=_stats_payload(item.out_of_sample).model_dump() if item.out_of_sample else None,
            notes=item.notes[:10],
            payload=candidate_payload(item.candidate),
        ))
    # 未过约束的候选只留少量，用于解释"为什么没选出来"
    for item in (result.get("rejected") or [])[:50]:
        session.add(AdvisorCandidate(
            run_id=run.id,
            family=item.candidate.family,
            primary_level=item.candidate.primary_level,
            entry_level=item.candidate.entry_level,
            description=item.candidate.describe()[:400],
            passed=False,
            rejected_reason=(item.rejected_reason or "")[:200],
            score=0.0,
            payload=candidate_payload(item.candidate),
        ))

    run.status = "completed"
    run.progress_percent = 100
    run.stage = "完成"
    run.verdict = result.get("verdict")
    run.summary = result.get("summary")
    run.profile = result.get("profile")
    run.evaluated_count = result.get("evaluated_count") or 0
    run.truncated = bool(result.get("budget_truncated"))
    run.engine_version = ENGINE_VERSION
    run.data_range = {"levels": result.get("levels") or []}
    run.finished_at = datetime.now()
    await session.commit()


@router.post("/runs", response_model=AdvisorRunSummary, status_code=201,
             dependencies=[Depends(require_permission("advisor.run"))])
async def create_run(
    body: AdvisorRunCreate,
    user: User = Depends(require_permission("advisor.run")),
    session: AsyncSession = Depends(get_session),
):
    run = AdvisorRun(
        user_id=user.id,
        symbol=body.symbol,
        symbol_name=body.symbol_name,
        market=body.market,
        status="pending",
        engine_version=ENGINE_VERSION,
        config=body.model_dump(),
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)

    task = asyncio.create_task(_run_analysis(run.id, body))
    _ACTIVE_TASKS.add(task)
    task.add_done_callback(_ACTIVE_TASKS.discard)

    return AdvisorRunSummary(
        id=run.id, symbol=run.symbol, symbol_name=run.symbol_name,
        status=run.status, created_at=run.created_at.isoformat() if run.created_at else None,
    )


@router.get("/runs", response_model=list[AdvisorRunSummary],
            dependencies=[Depends(require_permission("advisor.view"))])
async def list_runs(
    user: User = Depends(require_permission("advisor.view")),
    session: AsyncSession = Depends(get_session),
):
    runs = (await session.execute(
        select(AdvisorRun).where(AdvisorRun.user_id == user.id)
        .order_by(AdvisorRun.id.desc()).limit(30)
    )).scalars().all()
    return [
        AdvisorRunSummary(
            id=item.id, symbol=item.symbol, symbol_name=item.symbol_name,
            status=item.status, verdict=item.verdict, summary=item.summary,
            created_at=item.created_at.isoformat() if item.created_at else None,
        )
        for item in runs
    ]


@router.get("/runs/{run_id}", response_model=AdvisorRunResponse,
            dependencies=[Depends(require_permission("advisor.view"))])
async def get_run(
    run_id: int,
    user: User = Depends(require_permission("advisor.view")),
    session: AsyncSession = Depends(get_session),
):
    run = await session.get(AdvisorRun, run_id)
    if run is None or run.user_id != user.id:
        raise HTTPException(status_code=404, detail="分析记录不存在")

    rows = (await session.execute(
        select(AdvisorCandidate).where(AdvisorCandidate.run_id == run_id)
        .order_by(AdvisorCandidate.passed.desc(), AdvisorCandidate.rank.is_(None), AdvisorCandidate.rank)
    )).scalars().all()

    candidates = [
        AdvisorCandidateItem(
            rank=item.rank, family=item.family, primary_level=item.primary_level,
            entry_level=item.entry_level, description=item.description,
            score=item.score, passed=item.passed, plateau_stable=item.plateau_stable,
            rejected_reason=item.rejected_reason,
            in_sample=AdvisorTradeStats.model_validate(item.in_sample) if item.in_sample else None,
            out_of_sample=AdvisorTradeStats.model_validate(item.out_of_sample) if item.out_of_sample else None,
            notes=item.notes or [],
        )
        for item in rows
    ]

    return AdvisorRunResponse(
        id=run.id, symbol=run.symbol, symbol_name=run.symbol_name, market=run.market,
        status=run.status, progress_percent=run.progress_percent, stage=run.stage,
        error=run.error, verdict=run.verdict, summary=run.summary, profile=run.profile,
        evaluated_count=run.evaluated_count, truncated=run.truncated,
        engine_version=run.engine_version, config=run.config,
        created_at=run.created_at.isoformat() if run.created_at else None,
        finished_at=run.finished_at.isoformat() if run.finished_at else None,
        candidates=candidates,
    )


@router.post("/runs/{run_id}/template", response_model=AdvisorTemplateResponse,
             dependencies=[Depends(require_permission("advisor.run"))])
async def save_template(
    run_id: int,
    body: AdvisorTemplateSave,
    user: User = Depends(require_permission("advisor.run")),
    session: AsyncSession = Depends(get_session),
):
    """把建议落成真实策略模板（可在策略/选股/通知里直接使用）。"""
    run = await session.get(AdvisorRun, run_id)
    if run is None or run.user_id != user.id:
        raise HTTPException(status_code=404, detail="分析记录不存在")
    if run.verdict != "推荐":
        raise HTTPException(status_code=400, detail="该分析结论不可推荐，无法生成策略")

    top = (await session.execute(
        select(AdvisorCandidate).where(
            AdvisorCandidate.run_id == run_id, AdvisorCandidate.passed.is_(True),
        ).order_by(AdvisorCandidate.rank).limit(1)
    )).scalar_one_or_none()
    if top is None:
        raise HTTPException(status_code=400, detail="没有可用的候选")

    if not top.payload:
        raise HTTPException(status_code=400, detail="候选缺少结构化规则，无法生成策略")

    service = get_advisor_service()
    result = CandidateResult(candidate=candidate_from_payload(top.payload))
    template_payload = service.to_template(result, name=body.name)
    exists = await session.get(Template, template_payload.id)
    if exists is not None and exists.user_id == user.id:
        raise HTTPException(status_code=409, detail="该建议已生成过策略")

    template = Template(
        id=template_payload.id,
        user_id=user.id,
        name=template_payload.name,
        logic=template_payload.logic,
        condition_groups=[group.model_dump() for group in template_payload.condition_groups],
        primary_tf=template_payload.primary_tf,
        secondary_tfs=template_payload.secondary_tfs,
        enabled=body.enabled,
        trade_params=template_payload.trade_params.model_dump() if template_payload.trade_params else None,
    )
    session.add(template)

    recommendation = AdvisorRecommendation(
        run_id=run_id, user_id=user.id, symbol=run.symbol,
        template_id=template.id, status="active",
        baseline_profile=run.profile, review_after_bars=20, drift_state="unknown",
    )
    session.add(recommendation)
    await session.commit()

    return AdvisorTemplateResponse(
        template_id=template.id, name=template.name,
        primary_tf=template.primary_tf, secondary_tfs=template.secondary_tfs or [],
    )


@router.get("/recommendations", response_model=list[AdvisorRecommendationItem],
            dependencies=[Depends(require_permission("advisor.view"))])
async def list_recommendations(
    user: User = Depends(require_permission("advisor.view")),
    session: AsyncSession = Depends(get_session),
):
    rows = (await session.execute(
        select(AdvisorRecommendation).where(AdvisorRecommendation.user_id == user.id)
        .order_by(AdvisorRecommendation.id.desc()).limit(50)
    )).scalars().all()
    return [
        AdvisorRecommendationItem(
            id=item.id, run_id=item.run_id, symbol=item.symbol, template_id=item.template_id,
            status=item.status, drift_state=item.drift_state, drift_detail=item.drift_detail,
            review_after_bars=item.review_after_bars, baseline_profile=item.baseline_profile,
            created_at=item.created_at.isoformat() if item.created_at else None,
        )
        for item in rows
    ]


@router.post("/recommendations/{recommendation_id}/check", response_model=AdvisorRecommendationItem,
             dependencies=[Depends(require_permission("advisor.run"))])
async def check_recommendation(
    recommendation_id: int,
    user: User = Depends(require_permission("advisor.run")),
    session: AsyncSession = Depends(get_session),
):
    """复核一条建议是否发生漂移（画像变化 / 表现退化）。"""
    item = await session.get(AdvisorRecommendation, recommendation_id)
    if item is None or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="建议不存在")

    service: AdvisorService = get_advisor_service()
    drift_state, detail = await service.check_drift(item.symbol, item.baseline_profile or {})
    item.drift_state = drift_state
    item.drift_detail = detail
    await session.commit()

    return AdvisorRecommendationItem(
        id=item.id, run_id=item.run_id, symbol=item.symbol, template_id=item.template_id,
        status=item.status, drift_state=item.drift_state, drift_detail=item.drift_detail,
        review_after_bars=item.review_after_bars, baseline_profile=item.baseline_profile,
        created_at=item.created_at.isoformat() if item.created_at else None,
    )
