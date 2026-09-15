from __future__ import annotations

import json
from collections import defaultdict

from app.engine.chan import ChanResult
from app.schemas.signal import (
    ConditionGroupSchema,
    ConditionTemplateSchema,
    IndicatorValue,
    SignalResult,
    TimeframeValue,
)
from app.services.chan_service import ChanService
from app.services.condition_service import ConditionService
from app.services.data_service import DataService
from app.services.indicator_service import IndicatorService


def indicator_data_key(indicator_type: str, params: dict[str, float]) -> str:
    """生成可区分同类型不同参数的稳定指标键。"""
    encoded = json.dumps(params, sort_keys=True, separators=(",", ":"))
    return f"{indicator_type}:{encoded}"


def required_kline_limit(
    requested_limit: int,
    requirements: dict[str, IndicatorValue],
) -> int:
    """确保长周期均线在实时评估时也有完整样本。"""
    ma_periods = [
        int(requirement.params.get("period", 0))
        for requirement in requirements.values()
        if requirement.indicator_type == "ma"
    ]
    chip_lookbacks = [
        int(requirement.params.get("lookback", 0))
        for requirement in requirements.values()
        if requirement.indicator_type == "chip_distribution"
    ]
    return max(requested_limit, max(ma_periods, default=0) + 1, max(chip_lookbacks, default=0))


def _collect_requirements(
    template: ConditionTemplateSchema,
    groups: list[ConditionGroupSchema],
) -> tuple[list[str], dict[str, dict[str, IndicatorValue]]]:
    primary_tf = template.primary_tf or "1d"
    timeframes = {primary_tf, *template.secondary_tfs}
    indicators: dict[str, dict[str, IndicatorValue]] = defaultdict(dict)

    def inspect(value, timeframe: str):
        if isinstance(value, TimeframeValue):
            timeframes.add(value.timeframe_id)
            inspect(value.inner, value.timeframe_id)
        elif isinstance(value, IndicatorValue):
            timeframes.add(timeframe)
            indicators[timeframe][indicator_data_key(value.indicator_type, value.params)] = value

    for group in groups:
        for condition in group.conditions:
            if not condition.enabled:
                continue
            timeframe = condition.timeframe_id or primary_tf
            timeframes.add(timeframe)
            inspect(condition.left, timeframe)
            inspect(condition.right, timeframe)
            inspect(condition.right2, timeframe)

    return sorted(timeframes), indicators


async def load_template_context(
    symbol: str,
    template: ConditionTemplateSchema,
    data_service: DataService,
    chan_service: ChanService,
    indicator_service: IndicatorService,
    *,
    groups: list[ConditionGroupSchema] | None = None,
    kline_limit: int = 200,
) -> tuple[
    dict[str, list[dict]],
    dict[str, ChanResult],
    dict[str, dict[str, list[dict]]],
]:
    """加载一次策略评估所需的全部周期、缠论和参数化指标数据。"""
    requested_groups = groups if groups is not None else list(template.condition_groups)
    timeframes, indicator_requirements = _collect_requirements(template, requested_groups)
    kline_data: dict[str, list[dict]] = {}
    chan_data: dict[str, ChanResult] = {}
    indicator_data: dict[str, dict[str, list[dict]]] = {}

    for timeframe in timeframes:
        # 实时评估默认只取 200 根，但 MA260 至少需要 260 根完整样本。
        timeframe_limit = required_kline_limit(
            kline_limit,
            indicator_requirements.get(timeframe, {}),
        )
        kline_result = await data_service.fetch_klines(
            symbol=symbol,
            timeframe=timeframe,
            limit=timeframe_limit,
        )
        klines = kline_result["data"]
        kline_data[timeframe] = klines
        chan_data[timeframe] = await chan_service.analyze(symbol, timeframe, klines)
        indicator_data[timeframe] = {}

        daily_klines_for_chip = None
        if any(
            requirement.indicator_type == "chip_distribution"
            for requirement in indicator_requirements.get(timeframe, {}).values()
        ) and timeframe != "1d":
            chip_lookback = max(
                int(requirement.params.get("lookback", 500))
                for requirement in indicator_requirements[timeframe].values()
                if requirement.indicator_type == "chip_distribution"
            )
            daily_result = await data_service.fetch_klines(
                symbol=symbol,
                timeframe="1d",
                limit=min(max(chip_lookback, 500), 1000),
            )
            daily_klines_for_chip = daily_result["data"]

        for key, requirement in indicator_requirements.get(timeframe, {}).items():
            try:
                result = await indicator_service.calculate(
                    symbol,
                    timeframe,
                    requirement.indicator_type,
                    requirement.params,
                    klines,
                    context={"daily_klines": daily_klines_for_chip}
                    if requirement.indicator_type == "chip_distribution" and daily_klines_for_chip
                    else None,
                )
                indicator_data[timeframe][key] = result.values
                # 保留旧的 type-only 键，兼容尚未携带 params 的调用方。
                indicator_data[timeframe].setdefault(requirement.indicator_type, result.values)
            except Exception:
                indicator_data[timeframe][key] = []

    return kline_data, chan_data, indicator_data


async def evaluate_template_for_symbol(
    symbol: str,
    template: ConditionTemplateSchema,
    data_service: DataService,
    chan_service: ChanService,
    indicator_service: IndicatorService,
    condition_service: ConditionService,
    *,
    kline_limit: int = 200,
) -> SignalResult:
    kline_data, chan_data, indicator_data = await load_template_context(
        symbol,
        template,
        data_service,
        chan_service,
        indicator_service,
        kline_limit=kline_limit,
    )
    return await condition_service.evaluate(template, kline_data, chan_data, indicator_data)
