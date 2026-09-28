"""策略建议服务：物化 → 画像 → 搜索 → 落成真实策略模板。

设计要点：
- **物化**：每个级别只取一次K线、只算一次缠论/指标，供成千上万个候选复用；
- **搜索**：用 engine/advisor 的快速评估器排序；
- **确认**：把胜出候选落成真实模板后，由既有的 BacktestService 复核一遍，
  报告里给出的是真实回测的数字，避免"自建评估器"和线上口径不一致。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Awaitable, Callable

from app.engine.advisor.profile import basic_profile, chan_quality
from app.engine.advisor.registry import (
    EXIT_GRID,
    SUPPORTED_LEVELS,
    build_candidate_space,
)
from app.engine.advisor.scoring import Constraints
from app.engine.advisor.search import SearchConfig, search
from app.engine.advisor.types import Candidate, CandidateResult, ExitSpec, LevelSeries, Rule, indicator_key
from app.engine.chan import ChanResult
from app.schemas.signal import ConditionTemplateSchema
from app.services.backtest_service import BacktestService
from app.services.chan_service import ChanService
from app.services.data_service import DataService
from app.services.indicator_service import IndicatorService

logger = logging.getLogger(__name__)

ENGINE_VERSION = "1"
DEFAULT_KLINE_LIMIT = 500
ProgressCallback = Callable[[str, int], Awaitable[None]]


def _params_of(key: str) -> dict:
    params: dict = {}
    for part in key.split(":")[1:]:
        if "=" not in part:
            continue
        name, _, value = part.partition("=")
        try:
            number = float(value)
        except ValueError:
            continue
        params[name] = int(number) if number.is_integer() else number
    return params


def _indicator_type_of(key: str) -> str:
    return key.split(":", 1)[0]


def required_indicators(candidates: list[Candidate]) -> dict[str, set[tuple[str, tuple]]]:
    """从候选空间反推需要物化哪些指标：级别 -> {(指标类型, 参数元组)}。"""
    needed: dict[str, set[tuple[str, tuple]]] = {}
    for candidate in candidates:
        rule = candidate.entry
        for key, level in ((rule.left_key, candidate.entry_level), (rule.right_key, candidate.entry_level)):
            if not key:
                continue
            params = _params_of(key)
            needed.setdefault(level, set()).add(
                (_indicator_type_of(key), tuple(sorted(params.items())))
            )
    return needed


class AdvisorService:
    def __init__(
        self,
        data: DataService,
        chan: ChanService,
        indicator: IndicatorService,
        backtest: BacktestService,
    ):
        self._data = data
        self._chan = chan
        self._indicator = indicator
        self._backtest = backtest

    # ── 物化 ────────────────────────────────────────────────────────────

    async def materialize(
        self,
        symbol: str,
        candidates: list[Candidate],
        *,
        levels: tuple[str, ...] = SUPPORTED_LEVELS,
        limit: int = DEFAULT_KLINE_LIMIT,
        need_chan: bool = True,
    ) -> tuple[dict[str, LevelSeries], list[str]]:
        """把一个标的的各级别数据算好，供后续所有候选复用。"""
        needed = required_indicators(candidates)
        materialized: dict[str, LevelSeries] = {}
        notes: list[str] = []

        for level in levels:
            try:
                kline_result = await self._data.fetch_klines(symbol=symbol, timeframe=level, limit=limit)
            except Exception as error:  # 某个级别取数失败不影响其它级别
                notes.append(f"{level} 取数失败：{error}")
                logger.warning("advisor materialize %s %s failed: %s", symbol, level, error)
                continue
            bars = kline_result.get("data") or []
            if len(bars) < 30:
                notes.append(f"{level} 数据不足（{len(bars)} 根），已跳过")
                continue

            series = LevelSeries(
                level=level,
                times=[int(bar["open_time"]) for bar in bars],
                opens=[float(bar.get("open", bar["close"])) for bar in bars],
                highs=[float(bar["high"]) for bar in bars],
                lows=[float(bar["low"]) for bar in bars],
                closes=[float(bar["close"]) for bar in bars],
                volumes=[float(bar.get("volume", 0.0)) for bar in bars],
            )

            for indicator_type, params_tuple in sorted(needed.get(level, set())):
                params = dict(params_tuple)
                try:
                    result = await self._indicator.calculate(symbol, level, indicator_type, params, bars)
                except Exception as error:
                    notes.append(f"{level} {indicator_type} 计算失败：{error}")
                    continue
                key = indicator_key(indicator_type, params)
                fields: set[str] = set()
                for row in result.values:
                    fields.update(row.keys())
                fields.discard("time")
                series.indicators[key] = {
                    field: [row.get(field) for row in result.values] for field in sorted(fields)
                }

            if need_chan:
                try:
                    analysis = await self._chan.analyze(symbol, level, bars)
                    series.chan_points = _chan_points_of(analysis)
                except Exception as error:
                    notes.append(f"{level} 缠论计算失败：{error}")

            materialized[level] = series

        return materialized, notes

    # ── 单次分析 ────────────────────────────────────────────────────────

    async def analyze(
        self,
        symbol: str,
        *,
        constraints: Constraints | None = None,
        selection_ratio: float = 0.7,
        segments: int = 3,
        budget: int = 4000,
        limit: int = DEFAULT_KLINE_LIMIT,
        on_progress: ProgressCallback | None = None,
    ) -> dict:
        """完整分析：返回可直接落库/展示的结果字典。"""
        constraints = constraints or Constraints()
        config = SearchConfig(
            constraints=constraints, selection_ratio=selection_ratio,
            segments=segments, budget=budget,
        )

        async def report(stage: str, percent: int) -> None:
            if on_progress:
                await on_progress(stage, percent)

        await report("生成候选空间", 5)
        candidates, truncated = build_candidate_space(budget=budget)

        await report("物化行情与指标", 15)
        levels, notes = await self.materialize(symbol, candidates, limit=limit)

        if not levels:
            return {
                "verdict": "数据不足",
                "summary": "该标的没有可用于分析的行情数据。" + ("；".join(notes) if notes else ""),
                "profile": None,
                "candidates": [],
                "truncated": truncated,
                "evaluated_count": 0,
                "notes": notes,
            }

        await report("评估候选策略", 55)
        outcome = search(candidates, levels, config)

        await report("生成标的画像", 75)
        profile, recommendation, verdict, summary = await self._conclude(symbol, outcome, levels, config)

        await report("完成", 100)
        return {
            "verdict": verdict,
            "summary": summary,
            "profile": profile,
            "budget_truncated": truncated,
            "evaluated_count": outcome.evaluated,
            "results": outcome.results,
            "rejected": outcome.rejected,
            "recommendation": recommendation,
            "selection_bounds": outcome.selection_bounds,
            "holdout_bounds": outcome.holdout_bounds,
            "levels": sorted(levels.keys()),
            "notes": notes + outcome.notes,
        }

    async def _conclude(
        self,
        symbol: str,
        outcome,
        levels: dict[str, LevelSeries],
        config: SearchConfig,
    ) -> tuple[dict | None, CandidateResult | None, str, str]:
        """给出结论：是否可推荐、推荐哪个、以及理由。"""
        if not outcome.results:
            # 用淘汰原因区分"数据不足"和"有数据但没有稳定优势"
            reasons = [item.rejected_reason or "" for item in outcome.rejected]
            insufficient = reasons and all("交易数不足" in reason for reason in reasons)
            verdict = "数据不足" if insufficient else "无稳定优势"
            summary = (
                f"评估了 {outcome.evaluated} 个候选，没有候选同时满足约束条件。"
                + (f"主要原因：{reasons[0]}。" if reasons else "")
            )
            return None, None, verdict, summary

        # 先按"参数平台稳定"筛，再在稳定候选里选最优——
        # 否则最高分恰好是参数尖峰时，整份分析会被否掉，而明明存在稳定的候选。
        stable = [item for item in outcome.results if item.plateau_stable]
        if not stable:
            return None, None, "无稳定优势", (
                f"评估了 {outcome.evaluated} 个候选，通过约束的有 {len(outcome.results)} 个，"
                "但全部存在参数尖峰问题（相邻参数明显更差），说明选出的参数不可靠。"
            )

        winner = stable[0]
        level = winner.candidate.primary_level
        series = levels.get(level)

        profile: dict | None = None
        if series is not None:
            bars = _bars_from(series)
            base = basic_profile(level, bars)
            quality = chan_quality(bars)
            profile = {
                "level": level,
                "bars": base.bars,
                "volatility_pct": base.volatility_pct,
                "atr_pct": base.atr_pct,
                "efficiency_ratio": base.efficiency_ratio,
                "gap_ratio": base.gap_ratio,
                "tags": base.tags,
                "chan": {
                    "verdict": quality.verdict,
                    "zhongshu_count": quality.zhongshu_count,
                    "zhongshu_break_rate": quality.zhongshu_break_rate,
                    "point_count": quality.point_count,
                    "redraw_rate": quality.redraw_rate,
                    "forward_edge": quality.forward_edge,
                    "reasons": quality.reasons,
                },
            }

        holdout_positive = winner.out_of_sample.total_return > 0
        if not holdout_positive:
            return profile, winner, "无稳定优势", (
                f"最优候选（{winner.candidate.describe()}）选定期表现成立，"
                f"但留出期（样本外）收益为 {winner.out_of_sample.total_return:.2f}%，未通过样本外确认。"
            )

        summary = (
            f"推荐：{winner.candidate.describe()}。"
            f"选定期样本 {winner.in_sample.trades} 笔、胜率 {winner.in_sample.win_rate:.1f}%、"
            f"总收益 {winner.in_sample.total_return:.2f}%、最大回撤 {winner.in_sample.max_drawdown:.2f}%；"
            f"留出期（样本外）{winner.out_of_sample.trades} 笔、收益 {winner.out_of_sample.total_return:.2f}%。"
        )
        return profile, winner, "推荐", summary

    # ── 落成真实策略模板 ────────────────────────────────────────────────

    def to_template(self, result: CandidateResult, *, name: str | None = None) -> ConditionTemplateSchema:
        """把胜出候选转换成可直接使用的策略模板。"""
        candidate = result.candidate
        condition = _condition_of(candidate)
        trade_params = {
            "stop_loss_type": candidate.exit.stop_loss_type,
            "stop_loss_value": candidate.exit.stop_loss_value,
            "take_profit_type": candidate.exit.take_profit_type,
            "take_profit_value": candidate.exit.take_profit_value,
            "exit_conditions": [],
            "exit_logic": "OR",
        }
        return ConditionTemplateSchema.model_validate({
            "id": f"advisor_{candidate.id}"[:64],
            "name": (name or f"[建议] {candidate.describe()}")[:120],
            "logic": "AND",
            "primary_tf": candidate.primary_level,
            "secondary_tfs": [candidate.secondary_level] if candidate.secondary_level else [],
            "enabled": True,
            "condition_groups": [{
                "id": "advisor-entry",
                "name": "建议入场",
                "logic": "AND",
                "conditions": [condition],
            }],
            "trade_params": trade_params,
        })


    async def check_drift(self, symbol: str, baseline: dict) -> tuple[str, str]:
        """复核推荐是否漂移：画像变化或结构退化。

        默认判据（常量可调）：
          - 波动率相对基准变化超过 50%
          - 缠论信号重绘率超过基准的 1.5 倍
        """
        if not baseline or not baseline.get("level"):
            return "unknown", "缺少基准画像，无法复核"
        level = baseline["level"]
        try:
            kline_result = await self._data.fetch_klines(
                symbol=symbol, timeframe=level, limit=DEFAULT_KLINE_LIMIT,
            )
        except Exception as error:
            return "unknown", f"取数失败：{error}"
        bars = kline_result.get("data") or []
        if len(bars) < 60:
            return "unknown", "当前K线不足，无法复核"

        current = basic_profile(level, bars)
        baseline_volatility = float(baseline.get("volatility_pct") or 0.0)
        details: list[str] = []

        if baseline_volatility > 0:
            change = abs(current.volatility_pct - baseline_volatility) / baseline_volatility
            if change > DRIFT_VOLATILITY_RATIO:
                details.append(
                    f"波动率由 {baseline_volatility:.2f}% 变为 {current.volatility_pct:.2f}%（变化 {change:.0%}）"
                )

        baseline_redraw = (baseline.get("chan") or {}).get("redraw_rate")
        if baseline_redraw:
            quality = chan_quality(bars, redraw_checkpoints=2)
            if quality.redraw_rate and quality.redraw_rate > float(baseline_redraw) * DRIFT_REDRAW_RATIO:
                details.append(
                    f"缠论信号重绘率由 {float(baseline_redraw):.0%} 升到 {quality.redraw_rate:.0%}，结构变不稳"
                )

        if details:
            return "stale", "；".join(details)
        return "ok", "画像与基准一致，暂未发现漂移"


def _chan_points_of(analysis: ChanResult | None) -> dict[str, list[int]]:
    points: dict[str, list[int]] = {}
    if analysis is None:
        return points
    for item in analysis.buy_sell_points:
        if not item.confirmed:
            continue
        points.setdefault(item.type, []).append(int(item.time))
    return {key: sorted(value) for key, value in points.items()}


def _bars_from(series: LevelSeries) -> list[dict]:
    return [
        {
            "open_time": series.times[index],
            "open": series.opens[index],
            "high": series.highs[index],
            "low": series.lows[index],
            "close": series.closes[index],
            "volume": series.volumes[index],
        }
        for index in range(len(series.times))
    ]


def _series_condition(rule, level: str, timeframe_id: str | None) -> dict:
    def value_of(field: str | None, key: str | None, constant: float | None) -> dict:
        if constant is not None:
            return {"source": "constant", "value": constant}
        if key is None:
            return {"source": "price", "field": field or "close"}
        return {
            "source": "indicator",
            "indicator_type": _indicator_type_of(key),
            "params": _params_of(key),
            "field": field,
        }

    left = value_of(rule.left_field, rule.left_key, None)
    right = value_of(rule.right_field, rule.right_key, rule.right_value)
    operator = {
        ("cross", "above"): "crossAbove",
        ("cross", "below"): "crossBelow",
        ("compare", "above"): "gt",
        ("compare", "below"): "lt",
        ("direction", "rising"): "rising",
        ("direction", "falling"): "falling",
    }.get((rule.kind, rule.direction), "gt")
    condition = {
        "id": "advisor-condition",
        "name": rule.label[:120],
        "left": left,
        "operator": operator,
        "right": right,
        "enabled": True,
    }
    if timeframe_id:
        condition["timeframe_id"] = timeframe_id
    return condition


def _condition_of(candidate: Candidate) -> dict:
    rule = candidate.entry
    if rule.kind == "chan_point":
        # 缠论：级别用「次级周期」哨兵值，与模板声明的次级周期集合对应
        return {
            "id": "advisor-condition",
            "name": rule.label[:120],
            "left": {"source": "chan", "element": "buySellPoint", "property": rule.chan_point},
            "operator": "gt",
            "right": {"source": "constant", "value": 0},
            "timeframe_id": "secondary",
            "enabled": True,
        }
    # 指标类：入场在主周期时不写级别（走主周期）；取次级时同样用哨兵值
    if candidate.entry_level == candidate.primary_level:
        return _series_condition(rule, candidate.entry_level, None)
    return _series_condition(rule, candidate.entry_level, "secondary")


async def check_drift(self, symbol: str, baseline: dict) -> tuple[str, str]:
        """复核推荐是否漂移：画像变化或表现退化。

        默认判据（可用常量调整）：
          - 波动率相对基准变化超过 50%
          - 缠论重绘率超过基准的 1.5 倍
        """
        if not baseline or not baseline.get("level"):
            return "unknown", "缺少基准画像，无法复核"
        level = baseline["level"]
        try:
            kline_result = await self._data.fetch_klines(symbol=symbol, timeframe=level, limit=DEFAULT_KLINE_LIMIT)
        except Exception as error:
            return "unknown", f"取数失败：{error}"
        bars = kline_result.get("data") or []
        if len(bars) < 60:
            return "unknown", "当前K线不足，无法复核"

        current = basic_profile(level, bars)
        baseline_volatility = float(baseline.get("volatility_pct") or 0.0)
        details: list[str] = []

        if baseline_volatility > 0:
            change = abs(current.volatility_pct - baseline_volatility) / baseline_volatility
            if change > DRIFT_VOLATILITY_RATIO:
                details.append(
                    f"波动率由 {baseline_volatility:.2f}% 变为 {current.volatility_pct:.2f}%（变化 {change:.0%}）"
                )

        baseline_chan = baseline.get("chan") or {}
        baseline_redraw = baseline_chan.get("redraw_rate")
        quality = chan_quality(bars, redraw_checkpoints=2)
        if baseline_redraw and quality.redraw_rate:
            if quality.redraw_rate > float(baseline_redraw) * DRIFT_REDRAW_RATIO:
                details.append(
                    f"缠论信号重绘率由 {float(baseline_redraw):.0%} 升到 {quality.redraw_rate:.0%}，结构变不稳"
                )

        if details:
            return "stale", "；".join(details)
        return "ok", "画像与基准一致，暂未发现漂移"


# ── 候选的持久化与重建 ──────────────────────────────────────────────────

def candidate_payload(candidate: Candidate) -> dict:
    """把候选序列化成可落库的 JSON（落成真实模板时据此重建）。"""
    rule = candidate.entry
    return {
        "id": candidate.id,
        "family": candidate.family,
        "primary_level": candidate.primary_level,
        "entry_level": candidate.entry_level,
        "secondary_level": candidate.secondary_level,
        "entry": {
            "kind": rule.kind, "direction": rule.direction, "label": rule.label,
            "left_field": rule.left_field, "left_key": rule.left_key,
            "right_field": rule.right_field, "right_key": rule.right_key,
            "right_value": rule.right_value, "chan_point": rule.chan_point,
        },
        "exit": {
            "stop_loss_type": candidate.exit.stop_loss_type,
            "stop_loss_value": candidate.exit.stop_loss_value,
            "take_profit_type": candidate.exit.take_profit_type,
            "take_profit_value": candidate.exit.take_profit_value,
        },
    }


def candidate_from_payload(payload: dict) -> Candidate:
    entry = payload.get("entry") or {}
    exit_payload = payload.get("exit") or {}
    return Candidate(
        id=payload.get("id", "candidate"),
        family=payload.get("family", ""),
        primary_level=payload.get("primary_level", "1d"),
        entry_level=payload.get("entry_level") or payload.get("primary_level", "1d"),
        secondary_level=payload.get("secondary_level"),
        entry=Rule(
            kind=entry.get("kind", "compare"),
            direction=entry.get("direction", "above"),
            label=entry.get("label", ""),
            left_field=entry.get("left_field"),
            left_key=entry.get("left_key"),
            right_field=entry.get("right_field"),
            right_key=entry.get("right_key"),
            right_value=entry.get("right_value"),
            chan_point=entry.get("chan_point"),
        ),
        exit=ExitSpec(
            stop_loss_type=exit_payload.get("stop_loss_type", "atr"),
            stop_loss_value=exit_payload.get("stop_loss_value", 2.0),
            take_profit_type=exit_payload.get("take_profit_type", "rr_ratio"),
            take_profit_value=exit_payload.get("take_profit_value", 2.0),
        ),
    )


DRIFT_VOLATILITY_RATIO = 0.5
DRIFT_REDRAW_RATIO = 1.5


def exit_grid() -> tuple:
    return EXIT_GRID


def now() -> datetime:
    return datetime.now()
