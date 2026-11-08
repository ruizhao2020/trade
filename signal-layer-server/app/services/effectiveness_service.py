"""有效性评测服务：按股票池跑指标字段评测并落库。

输出是"字段级"结论：同一指标的不同字段、不同周期、不同池子分别成行，
前端按（类型, 字段, 参数, 周期）查结论来决定能不能进策略。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.indicator import INDICATOR_META
from app.engine.effectiveness import (
    FieldEvaluation,
    SymbolSeries,
    evaluate_continuous_field,
    evaluate_event_field,
)
from app.models.effectiveness import IndicatorEffectiveness

logger = logging.getLogger(__name__)

ENGINE_VERSION = "v1"
DEFAULT_UNIVERSE = "stock"
MIN_BARS = 120


def params_key(params: dict[str, Any]) -> str:
    """参数指纹：与顺序无关、定长，用于定位同一条评测单元。

    直接存 JSON 会超过列宽（量价有 9 个参数），这里存 sha1。
    """
    import hashlib

    raw = json.dumps(params, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def indicator_specs(indicator_types: Optional[list[str]] = None) -> list[dict]:
    """默认评测所有声明了 outputs 的指标，用指标库里的默认参数。"""
    names = indicator_types or [
        name for name, meta in INDICATOR_META.items() if meta.get("outputs")
    ]
    specs = []
    for name in names:
        meta = INDICATOR_META.get(name) or {}
        if not meta.get("outputs"):
            continue
        specs.append({
            "type": name,
            "name": meta.get("name", name),
            "params": dict(meta.get("default_params") or {}),
            "outputs": list(meta.get("outputs") or []),
        })
    return specs


class EffectivenessService:
    def __init__(self, data_service, indicator_service):
        self._data = data_service
        self._indicators = indicator_service

    async def collect_series(
        self, symbols: list[str], timeframe: str, limit: int, spec: dict,
    ) -> list[SymbolSeries]:
        """逐标的取数并计算指标；取数失败或样本不足的标的直接跳过。"""
        series: list[SymbolSeries] = []
        for symbol in symbols:
            try:
                payload = await self._data.fetch_klines(symbol, timeframe, limit=limit)
            except Exception as error:  # 单个标的失败不影响整体评测
                logger.warning("effectiveness: fetch %s failed: %s", symbol, error)
                continue
            bars = payload.get("data") or []
            if len(bars) < MIN_BARS:
                continue
            try:
                result = await self._indicators.calculate(
                    symbol, timeframe, spec["type"], spec["params"], bars,
                )
            except Exception as error:  # 某个指标在某标的上算不出来时跳过该标的
                logger.warning(
                    "effectiveness: %s on %s failed: %s", spec["type"], symbol, error,
                )
                continue
            series.append(SymbolSeries(
                symbol=symbol,
                closes=[float(bar["close"]) for bar in bars],
                times=[int(bar["open_time"]) for bar in bars],
                values=result.values,
            ))
        return series

    async def evaluate(
        self,
        session: AsyncSession,
        symbols: list[str],
        timeframe: str = "1d",
        limit: int = 800,
        universe: str = DEFAULT_UNIVERSE,
        indicator_types: Optional[list[str]] = None,
    ) -> list[IndicatorEffectiveness]:
        saved: list[IndicatorEffectiveness] = []
        for spec in indicator_specs(indicator_types):
            series = await self.collect_series(symbols, timeframe, limit, spec)
            if not series:
                logger.warning("effectiveness: %s has no usable series", spec["type"])
                continue
            for output in spec["outputs"]:
                field_name = output.get("field")
                if not field_name:
                    continue
                if output.get("kind") == "event":
                    evaluation = evaluate_event_field(
                        series, field_name, output.get("direction") or "none",
                    )
                else:
                    evaluation = evaluate_continuous_field(series, field_name)
                saved.append(await self._save(
                    session, spec, timeframe, universe, evaluation, len(series),
                ))
        return saved

    async def _save(
        self,
        session: AsyncSession,
        spec: dict,
        timeframe: str,
        universe: str,
        evaluation: FieldEvaluation,
        symbol_count: int,
    ) -> IndicatorEffectiveness:
        key = params_key(spec["params"])
        # 方向是评测结论而不是评测单元：重评后方向可能翻转，
        # 这里按"类型+字段+参数+周期+池子+持有期"定位旧行，并清掉其它方向的残留。
        existing_rows = (await session.execute(
            select(IndicatorEffectiveness).where(
                IndicatorEffectiveness.indicator_type == spec["type"],
                IndicatorEffectiveness.field == evaluation.field,
                IndicatorEffectiveness.params_key == key,
                IndicatorEffectiveness.timeframe == timeframe,
                IndicatorEffectiveness.universe == universe,
                IndicatorEffectiveness.horizon == 10,
            ).order_by(IndicatorEffectiveness.id)
        )).scalars().all()
        existing = existing_rows[0] if existing_rows else None
        for stale in existing_rows[1:]:
            await session.delete(stale)
        if existing_rows[1:]:
            # 先落删除再改方向：否则旧方向的残留行会和更新后的行撞唯一键。
            await session.flush()

        values = {
            "params": spec["params"],
            "direction": evaluation.direction,
            "sample_n": evaluation.sample_n,
            "raw_events": evaluation.raw_events,
            "hit_rate": evaluation.hit_rate,
            "avg_return": evaluation.avg_return,
            "baseline_return": evaluation.baseline_return,
            "excess_return": evaluation.excess_return,
            "p_value": evaluation.p_value,
            "decay": {str(key): value for key, value in evaluation.decay.items()},
            "stability": evaluation.stability,
            "verdict": evaluation.verdict,
            "scope": {
                "symbols": symbol_count,
                "rule": evaluation.rule,
                "threshold": evaluation.threshold,
            },
            "engine_version": ENGINE_VERSION,
        }
        if existing is not None:
            for name, value in values.items():
                setattr(existing, name, value)
            return existing

        row = IndicatorEffectiveness(
            indicator_type=spec["type"],
            field=evaluation.field,
            params_key=key,
            timeframe=timeframe,
            universe=universe,
            horizon=10,
            **values,
        )
        session.add(row)
        return row
