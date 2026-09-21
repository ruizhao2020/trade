from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.engine.indicator.base import (
    IndicatorCalculator, IndicatorResult, PlotSpec, ProfileData,
    ProfileSnapshot, RenderSpec, register_indicator,
)

CN_TZ = timezone(timedelta(hours=8))


def _trade_date(open_time: int):
    return datetime.fromtimestamp(open_time / 1000, CN_TZ).date()


def _weighted_quantile(prices: list[float], weights: list[float], quantile: float) -> float:
    cumulative = 0.0
    for price, weight in zip(prices, weights):
        cumulative += weight
        if cumulative >= quantile:
            return price
    return prices[-1]


def _concentration(low: float, high: float) -> float:
    denominator = low + high
    return (high - low) / denominator * 100 if denominator > 0 else 0.0


def _bar_distribution(prices: list[float], low: float, high: float, center: float) -> list[float]:
    if high <= low:
        nearest = min(range(len(prices)), key=lambda index: abs(prices[index] - center))
        return [1.0 if index == nearest else 0.0 for index in range(len(prices))]
    indices = [index for index, price in enumerate(prices) if low <= price <= high]
    if not indices:
        nearest = min(range(len(prices)), key=lambda index: abs(prices[index] - center))
        return [1.0 if index == nearest else 0.0 for index in range(len(prices))]
    result = [0.0] * len(prices)
    left_span = max(center - low, (high - low) / len(prices), 1e-12)
    right_span = max(high - center, (high - low) / len(prices), 1e-12)
    for index in indices:
        price = prices[index]
        distance = (center - price) / left_span if price <= center else (price - center) / right_span
        result[index] = max(1.0 - distance, 0.05)
    total = sum(result)
    return [value / total for value in result]


def _turnover_fraction(bar: dict) -> float | None:
    turnover_rate = bar.get("turnover_rate")
    if turnover_rate is None:
        shares = float(bar.get("circulating_shares") or 0)
        volume = float(bar.get("volume") or 0)
        turnover_rate = volume / shares * 100 if shares > 0 else None
    if turnover_rate is None or float(turnover_rate) <= 0:
        return None
    return min(float(turnover_rate) / 100, 1.0)


def _apply_bar(
    profile: list[float], prices: list[float], bar: dict,
    turnover: float, price_factor: float = 1.0,
) -> list[float]:
    low = float(bar["low"]) * price_factor
    high = float(bar["high"]) * price_factor
    volume = float(bar.get("volume") or 0)
    amount = float(bar.get("amount") or bar.get("turnover") or 0)
    fallback = (low + high + float(bar["close"]) * price_factor) / 3
    average_price = amount / volume * price_factor if volume > 0 and amount > 0 else fallback
    center = min(max(average_price, low), high)
    distributed = _bar_distribution(prices, low, high, center)
    if sum(profile) <= 0:
        return distributed
    remaining = 1.0 - turnover
    return [old * remaining + new * turnover for old, new in zip(profile, distributed)]


def _profile_metrics(
    prices: list[float], profile: list[float], current_price: float,
    valid_turnover_days: int, coverage_ratio: float,
    baseline_days: int, intraday_bars: int,
    near_range_pct: float, support_range_pct: float,
    peak_prominence: float, min_peak_distance: int,
) -> dict[str, float]:
    total = sum(profile)
    weights = [weight / total for weight in profile]
    average_cost = sum(price * weight for price, weight in zip(prices, weights))
    profit_ratio = sum(weight for price, weight in zip(prices, weights) if price <= current_price) * 100
    range70_low = _weighted_quantile(prices, weights, 0.15)
    range70_high = _weighted_quantile(prices, weights, 0.85)
    range90_low = _weighted_quantile(prices, weights, 0.05)
    range90_high = _weighted_quantile(prices, weights, 0.95)
    smoothed_weights = [
        sum(weights[max(0, index - 2):min(len(weights), index + 3)])
        / len(weights[max(0, index - 2):min(len(weights), index + 3)])
        for index in range(len(weights))
    ]
    maximum_weight = max(smoothed_weights)
    peak_candidates = [
        index for index, weight in enumerate(smoothed_weights)
        if weight >= maximum_weight * peak_prominence
        and weight >= (smoothed_weights[index - 1] if index > 0 else -1)
        and weight >= (smoothed_weights[index + 1] if index + 1 < len(weights) else -1)
    ]
    selected_peaks: list[int] = []
    for candidate in sorted(peak_candidates, key=lambda index: smoothed_weights[index], reverse=True):
        if all(abs(candidate - selected) >= min_peak_distance for selected in selected_peaks):
            selected_peaks.append(candidate)
    raw_peak_index = max(range(len(prices)), key=lambda index: weights[index])
    primary_index = selected_peaks[0] if selected_peaks else raw_peak_index
    secondary_index = selected_peaks[1] if len(selected_peaks) > 1 else None
    peak_half_width = max(1, min_peak_distance // 2)
    dominant_peak_ratio = sum(
        weights[max(0, primary_index - peak_half_width):min(len(weights), primary_index + peak_half_width + 1)]
    ) * 100
    secondary_peak_ratio = sum(
        weights[max(0, secondary_index - peak_half_width):min(len(weights), secondary_index + peak_half_width + 1)]
    ) * 100 if secondary_index is not None else 0.0
    near_low = current_price * (1 - near_range_pct / 100)
    near_high = current_price * (1 + near_range_pct / 100)
    support_low = current_price * (1 - support_range_pct / 100)
    pressure_high = current_price * (1 + support_range_pct / 100)
    return {
        "current_price": current_price, "peak_price": prices[primary_index],
        "average_cost": average_cost, "profit_ratio": profit_ratio,
        "range70_low": range70_low, "range70_high": range70_high,
        "concentration70": _concentration(range70_low, range70_high),
        "range90_low": range90_low, "range90_high": range90_high,
        "concentration90": _concentration(range90_low, range90_high),
        "dominant_peak_ratio": dominant_peak_ratio,
        "secondary_peak_price": prices[secondary_index] if secondary_index is not None else 0.0,
        "secondary_peak_ratio": secondary_peak_ratio,
        "peak_separation_pct": (
            abs(prices[primary_index] - prices[secondary_index]) / prices[primary_index] * 100
            if secondary_index is not None and prices[primary_index] else 0.0
        ),
        "peak_count": float(len(selected_peaks)),
        "single_peak": 1.0 if len(selected_peaks) == 1 else 0.0,
        "double_peak": 1.0 if len(selected_peaks) == 2 else 0.0,
        "upper_chip_ratio": sum(weight for price, weight in zip(prices, weights) if price > current_price) * 100,
        "support_chip_ratio": sum(
            weight for price, weight in zip(prices, weights)
            if support_low <= price <= current_price
        ) * 100,
        "pressure_chip_ratio": sum(
            weight for price, weight in zip(prices, weights)
            if current_price < price <= pressure_high
        ) * 100,
        "near_price_chip_ratio": sum(
            weight for price, weight in zip(prices, weights)
            if near_low <= price <= near_high
        ) * 100,
        "valid_turnover_days": float(valid_turnover_days),
        "coverage_ratio": coverage_ratio, "baseline_days": float(baseline_days),
        "intraday_bars": float(intraday_bars),
    }


def _pct_change(current: float, previous: float) -> float:
    return (current - previous) / abs(previous) * 100 if previous else 0.0


def _enrich_snapshot_metrics(
    snapshots: list[ProfileSnapshot], params: dict[str, int | float],
) -> None:
    """把静态筹码快照转换为可供策略和回测使用的因果时间序列。"""
    trend_period = int(params["trend_period"])
    migration_threshold = float(params["migration_threshold_pct"])
    concentration_threshold = float(params["concentration_change_threshold"])
    pressure_release_threshold = float(params["pressure_release_threshold"])
    retest_tolerance = float(params["retest_tolerance_pct"])

    for index, snapshot in enumerate(snapshots):
        metrics = snapshot.metrics
        price = metrics["current_price"]
        peak = metrics["peak_price"]
        average = metrics["average_cost"]
        metrics.update({
            "price_vs_peak_pct": _pct_change(price, peak),
            "price_vs_average_pct": _pct_change(price, average),
            "above_peak": 1.0 if price >= peak else 0.0,
            "above_average_cost": 1.0 if price >= average else 0.0,
            "inside_range70": 1.0 if metrics["range70_low"] <= price <= metrics["range70_high"] else 0.0,
            "inside_range90": 1.0 if metrics["range90_low"] <= price <= metrics["range90_high"] else 0.0,
            "cost_position": (
                -2.0 if price < metrics["range90_low"]
                else -1.0 if price < metrics["range70_low"]
                else 0.0 if price <= metrics["range70_high"]
                else 1.0 if price <= metrics["range90_high"]
                else 2.0
            ),
            "peak_change_pct": 0.0,
            "average_cost_change_pct": 0.0,
            "profit_ratio_change": 0.0,
            "concentration70_change": 0.0,
            "pressure_chip_change": 0.0,
            "support_chip_change": 0.0,
            "peak_direction": 0.0,
            "average_cost_direction": 0.0,
            "chip_converging": 0.0,
            "chip_spreading": 0.0,
            "cross_peak_up": 0.0,
            "cross_peak_down": 0.0,
            "cross_average_cost_up": 0.0,
            "cross_average_cost_down": 0.0,
            "break_range70_high": 0.0,
            "break_range70_low": 0.0,
            "retest_peak": 0.0,
            "single_peak_formed": 0.0,
            "double_peak_formed": 0.0,
            "peak_shifted_up": 0.0,
            "peak_shifted_down": 0.0,
            "concentration_started": 0.0,
            "pressure_released": 0.0,
            "support_strengthened": 0.0,
        })

        if index > 0:
            previous = snapshots[index - 1].metrics
            metrics.update({
                "cross_peak_up": 1.0 if previous["current_price"] <= previous["peak_price"] and price > peak else 0.0,
                "cross_peak_down": 1.0 if previous["current_price"] >= previous["peak_price"] and price < peak else 0.0,
                "cross_average_cost_up": 1.0 if previous["current_price"] <= previous["average_cost"] and price > average else 0.0,
                "cross_average_cost_down": 1.0 if previous["current_price"] >= previous["average_cost"] and price < average else 0.0,
                "break_range70_high": 1.0 if previous["current_price"] <= previous["range70_high"] and price > metrics["range70_high"] else 0.0,
                "break_range70_low": 1.0 if previous["current_price"] >= previous["range70_low"] and price < metrics["range70_low"] else 0.0,
                "single_peak_formed": 1.0 if metrics["single_peak"] > 0 and previous["single_peak"] <= 0 else 0.0,
                "double_peak_formed": 1.0 if metrics["double_peak"] > 0 and previous["double_peak"] <= 0 else 0.0,
            })
            previous_distance = _pct_change(previous["current_price"], previous["peak_price"])
            metrics["retest_peak"] = 1.0 if (
                previous_distance > retest_tolerance
                and 0 <= metrics["price_vs_peak_pct"] <= retest_tolerance
            ) else 0.0

        if index < trend_period:
            continue
        reference = snapshots[index - trend_period].metrics
        metrics["peak_change_pct"] = _pct_change(peak, reference["peak_price"])
        metrics["average_cost_change_pct"] = _pct_change(average, reference["average_cost"])
        metrics["profit_ratio_change"] = metrics["profit_ratio"] - reference["profit_ratio"]
        metrics["concentration70_change"] = metrics["concentration70"] - reference["concentration70"]
        metrics["pressure_chip_change"] = metrics["pressure_chip_ratio"] - reference["pressure_chip_ratio"]
        metrics["support_chip_change"] = metrics["support_chip_ratio"] - reference["support_chip_ratio"]
        metrics["peak_direction"] = (
            1.0 if metrics["peak_change_pct"] >= migration_threshold
            else -1.0 if metrics["peak_change_pct"] <= -migration_threshold
            else 0.0
        )
        metrics["average_cost_direction"] = (
            1.0 if metrics["average_cost_change_pct"] >= migration_threshold
            else -1.0 if metrics["average_cost_change_pct"] <= -migration_threshold
            else 0.0
        )
        metrics["chip_converging"] = 1.0 if metrics["concentration70_change"] <= -concentration_threshold else 0.0
        metrics["chip_spreading"] = 1.0 if metrics["concentration70_change"] >= concentration_threshold else 0.0
        previous_metrics = snapshots[index - 1].metrics
        metrics["peak_shifted_up"] = 1.0 if metrics["peak_direction"] > 0 and previous_metrics.get("peak_direction", 0) <= 0 else 0.0
        metrics["peak_shifted_down"] = 1.0 if metrics["peak_direction"] < 0 and previous_metrics.get("peak_direction", 0) >= 0 else 0.0
        metrics["concentration_started"] = 1.0 if metrics["chip_converging"] > 0 and previous_metrics.get("chip_converging", 0) <= 0 else 0.0
        metrics["pressure_released"] = 1.0 if metrics["pressure_chip_change"] <= -pressure_release_threshold else 0.0
        metrics["support_strengthened"] = 1.0 if metrics["support_chip_change"] >= pressure_release_threshold else 0.0


def _price_axis(ranges: list[tuple[float, float]], bins: int) -> list[float]:
    minimum = min(item[0] for item in ranges)
    maximum = max(item[1] for item in ranges)
    if maximum <= minimum:
        maximum = minimum + max(abs(minimum) * 0.01, 0.01)
    step = (maximum - minimum) / (bins - 1)
    return [minimum + step * index for index in range(bins)]


@register_indicator
class ChipDistributionCalculator(IndicatorCalculator):
    """以日线筹码为基准，支持日线和分钟级逐 K 线成本分布快照。"""

    @property
    def type(self) -> str:
        return "chip_distribution"

    @staticmethod
    def _render() -> RenderSpec:
        return RenderSpec(window="main", plots=[
            PlotSpec(field="weight", type="profile", color="#6c8cff", label="筹码峰"),
        ])

    @staticmethod
    def _params(params: dict[str, Any]) -> dict[str, int | float]:
        normalized = {
            "bins": int(params.get("bins", 120)),
            "lookback": int(params.get("lookback", 500)),
            "min_turnover_days": int(params.get("min_turnover_days", 20)),
            "near_range_pct": float(params.get("near_range_pct", 3.0)),
            "support_range_pct": float(params.get("support_range_pct", 5.0)),
            "peak_prominence": float(params.get("peak_prominence", 0.5)),
            "min_peak_distance": int(params.get("min_peak_distance", 5)),
            "trend_period": int(params.get("trend_period", 5)),
            "migration_threshold_pct": float(params.get("migration_threshold_pct", 1.0)),
            "concentration_change_threshold": float(params.get("concentration_change_threshold", 0.5)),
            "pressure_release_threshold": float(params.get("pressure_release_threshold", 5.0)),
            "retest_tolerance_pct": float(params.get("retest_tolerance_pct", 1.0)),
        }
        if not 40 <= normalized["bins"] <= 300:
            raise ValueError("筹码分布价格档位必须在 40 到 300 之间")
        if not 30 <= normalized["lookback"] <= 1000:
            raise ValueError("筹码分布回看周期必须在 30 到 1000 个交易日之间")
        if not 1 <= normalized["min_turnover_days"] <= normalized["lookback"]:
            raise ValueError("有效换手天数必须大于0且不超过回看周期")
        if not 0 < normalized["near_range_pct"] <= 20 or not 0 < normalized["support_range_pct"] <= 30:
            raise ValueError("筹码邻近与支撑压力范围必须为合理的正百分比")
        if not 0 < normalized["peak_prominence"] <= 1 or not 1 <= normalized["min_peak_distance"] <= 30:
            raise ValueError("筹码峰显著度或最小峰间距不合法")
        if not 1 <= normalized["trend_period"] <= 60:
            raise ValueError("筹码趋势周期必须在1到60之间")
        return normalized

    def calculate(self, klines: list[dict], params: dict[str, Any]) -> IndicatorResult:
        return self.calculate_with_context(klines, params, {})

    def calculate_with_context(
        self, klines: list[dict], params: dict[str, Any], context: dict,
    ) -> IndicatorResult:
        normalized = self._params(params)
        if not klines:
            return IndicatorResult(type=self.type, params=normalized, values=[], render=self._render())
        daily_klines = context.get("daily_klines")
        if daily_klines:
            return self._calculate_intraday(klines, daily_klines, normalized)
        return self._calculate_daily(klines, normalized)

    def _calculate_daily(self, klines: list[dict], params: dict[str, int | float]) -> IndicatorResult:
        bars = klines[-params["lookback"]:]
        valid_count = sum(1 for bar in bars if _turnover_fraction(bar) is not None)
        if valid_count < params["min_turnover_days"]:
            raise ValueError(
                f"筹码分布需要至少 {params['min_turnover_days']} 个交易日的换手率或流通股本数据，"
                f"当前只有 {valid_count} 天"
            )
        prices = _price_axis([(float(bar["low"]), float(bar["high"])) for bar in bars], params["bins"])
        profile = [0.0] * len(prices)
        snapshots: list[ProfileSnapshot] = []
        processed_valid = 0
        for processed_bars, bar in enumerate(bars, 1):
            turnover = _turnover_fraction(bar)
            if turnover is not None:
                profile = _apply_bar(profile, prices, bar, turnover)
                processed_valid += 1
            if sum(profile) <= 0:
                continue
            metrics = _profile_metrics(
                prices, profile, float(bar["close"]), processed_valid,
                processed_valid / processed_bars * 100, processed_valid, 0,
                float(params["near_range_pct"]), float(params["support_range_pct"]),
                float(params["peak_prominence"]), int(params["min_peak_distance"]),
            )
            snapshots.append(self._snapshot(bar, profile, metrics))
        return self._result(params, prices, snapshots)

    def _calculate_intraday(
        self, intraday_klines: list[dict], daily_klines: list[dict], params: dict[str, int | float],
    ) -> IndicatorResult:
        minute_bars = intraday_klines
        first_date = _trade_date(int(minute_bars[0]["open_time"]))
        daily_bars = daily_klines[-params["lookback"]:]
        baseline = [bar for bar in daily_bars if _trade_date(int(bar["open_time"])) < first_date]
        valid_baseline = [bar for bar in baseline if _turnover_fraction(bar) is not None]
        if len(valid_baseline) < params["min_turnover_days"]:
            raise ValueError(
                f"分钟筹码分布需要至少 {params['min_turnover_days']} 天日线换手数据作为基准，"
                f"当前只有 {len(valid_baseline)} 天"
            )
        sorted_daily = sorted(
            [(_trade_date(int(bar["open_time"])), bar) for bar in daily_bars],
            key=lambda item: item[0],
        )

        def daily_meta(timestamp: int) -> dict | None:
            target = _trade_date(timestamp)
            matched = None
            for trade_day, bar in sorted_daily:
                if trade_day > target:
                    break
                matched = bar
            return matched

        def minute_factor(bar: dict) -> float:
            meta = daily_meta(int(bar["open_time"]))
            factor = float((meta or {}).get("adjustment_factor") or 1.0)
            return 1 / factor if factor > 0 and bar.get("adjustment_type") != "qfq" else 1.0

        ranges = [(float(bar["low"]), float(bar["high"])) for bar in baseline]
        ranges.extend([
            (float(bar["low"]) * minute_factor(bar), float(bar["high"]) * minute_factor(bar))
            for bar in minute_bars
        ])
        prices = _price_axis(ranges, params["bins"])
        profile = [0.0] * len(prices)
        for bar in baseline:
            turnover = _turnover_fraction(bar)
            if turnover is not None:
                profile = _apply_bar(profile, prices, bar, turnover)

        snapshots: list[ProfileSnapshot] = []
        processed_minutes = 0
        for bar in minute_bars:
            meta = daily_meta(int(bar["open_time"]))
            shares = float((meta or {}).get("circulating_shares") or 0)
            volume = float(bar.get("volume") or 0)
            turnover = min(volume / shares, 1.0) if shares > 0 and volume > 0 else None
            factor = minute_factor(bar)
            if turnover is not None:
                profile = _apply_bar(profile, prices, bar, turnover, factor)
                processed_minutes += 1
            metrics = _profile_metrics(
                prices, profile, float(bar["close"]) * factor, len(valid_baseline),
                len(valid_baseline) / max(1, len(baseline)) * 100,
                len(valid_baseline), processed_minutes,
                float(params["near_range_pct"]), float(params["support_range_pct"]),
                float(params["peak_prominence"]), int(params["min_peak_distance"]),
            )
            snapshots.append(self._snapshot(bar, profile, metrics))
        return self._result(params, prices, snapshots)

    @staticmethod
    def _snapshot(bar: dict, profile: list[float], metrics: dict[str, float]) -> ProfileSnapshot:
        total = sum(profile)
        return ProfileSnapshot(
            time=int(bar["open_time"]),
            weights=[round(weight / total * 100, 6) for weight in profile],
            metrics={key: round(value, 8) for key, value in metrics.items()},
        )

    def _result(
        self, params: dict[str, int | float], prices: list[float], snapshots: list[ProfileSnapshot],
    ) -> IndicatorResult:
        _enrich_snapshot_metrics(snapshots, params)
        values = [{"time": float(snapshot.time), **snapshot.metrics} for snapshot in snapshots]
        return IndicatorResult(
            type=self.type, params=params, values=values, render=self._render(),
            profile_data=ProfileData(
                prices=[round(price, 8) for price in prices], snapshots=snapshots,
            ),
        )
