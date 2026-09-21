from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.engine.indicator.base import (
    IndicatorCalculator,
    IndicatorResult,
    MarkerSpec,
    RenderSpec,
    _get_times,
    register_indicator,
)


@dataclass
class Pivot:
    direction: Literal["top", "bottom"]
    center_index: int
    confirm_index: int
    price: float


@dataclass
class Segment:
    start_index: int
    end_index: int
    low: float
    high: float


@dataclass
class ReasonableZone:
    index: int
    start_index: int
    confirm_index: int
    low: float
    high: float
    fold_count: int


def _fractal_at(highs: list[float], lows: list[float], center: int) -> str | None:
    if center <= 0 or center + 1 >= len(highs):
        return None
    if (
        highs[center - 1] < highs[center] > highs[center + 1]
        and lows[center - 1] < lows[center] > lows[center + 1]
    ):
        return "top"
    if (
        lows[center - 1] > lows[center] < lows[center + 1]
        and highs[center - 1] > highs[center] < highs[center + 1]
    ):
        return "bottom"
    return None


def _overlap(segments: list[Segment]) -> tuple[float, float] | None:
    low = max(segment.low for segment in segments)
    high = min(segment.high for segment in segments)
    return (low, high) if low < high else None


@register_indicator
class DilunStructureCalculator(IndicatorCalculator):
    """帝论首版：确认分型、合理价格区间与三类价格事件。"""

    @property
    def type(self) -> str:
        return "dilun_structure"

    def calculate(self, klines: list[dict], params: dict[str, Any]) -> IndicatorResult:
        departure_confirm_bars = int(params.get("departure_confirm_bars", 2))
        true_departure_bars = int(params.get("true_departure_bars", 3))
        false_departure_max_bars = int(params.get("false_departure_max_bars", 5))
        retest_window = int(params.get("retest_window", 10))
        maturity_bars = int(params.get("maturity_bars", 8))
        maturity_folds = int(params.get("maturity_folds", 4))
        breakout_buffer_pct = float(params.get("breakout_buffer_pct", 0.0))
        if not 1 <= departure_confirm_bars <= 10:
            raise ValueError("脱离确认根数应在1到10之间")
        if true_departure_bars < departure_confirm_bars or true_departure_bars > 20:
            raise ValueError("真脱离根数不能小于脱离确认根数且不能超过20")
        if not 1 <= false_departure_max_bars <= 30 or not 1 <= retest_window <= 60:
            raise ValueError("假脱离或回归失败观察窗口不合法")
        if maturity_bars < 1 or maturity_folds < 3 or not 0 <= breakout_buffer_pct < 10:
            raise ValueError("态势成熟或突破缓冲参数不合法")

        times = _get_times(klines)
        opens = [float(item.get("open") or 0) for item in klines]
        highs = [float(item.get("high") or 0) for item in klines]
        lows = [float(item.get("low") or 0) for item in klines]
        closes = [float(item.get("close") or 0) for item in klines]
        values: list[dict[str, float]] = [
            {"time": float(timestamp), "close": closes[index]}
            for index, timestamp in enumerate(times)
        ]
        if len(klines) < 3:
            return self._result(params, values)

        pivots: list[Pivot] = []
        segments: list[Segment] = []
        active_zone: ReasonableZone | None = None
        zone_sequence = 0
        active_trend = 0
        pending_trend: Pivot | None = None

        outside_direction = 0
        outside_count = 0
        departure_direction = 0
        departure_index: int | None = None
        true_departure_emitted = False
        return_failure_emitted = False

        for index in range(len(klines)):
            confirmed_pivot: Pivot | None = None
            center = index - 1
            fractal_type = _fractal_at(highs, lows, center) if index >= 2 else None
            if fractal_type:
                price = highs[center] if fractal_type == "top" else lows[center]
                sign = -1.0 if fractal_type == "top" else 1.0
                confirmed_pivot = Pivot(fractal_type, center, index, price)
                values[center].update({
                    "fractal_marker": sign,
                    "fractal_price": price,
                })
                values[index].update({
                    "fractal_confirmed": sign,
                    "top_fractal_confirmed": 1.0 if fractal_type == "top" else 0.0,
                    "bottom_fractal_confirmed": 1.0 if fractal_type == "bottom" else 0.0,
                    "fractal_source_time": float(times[center]),
                    "fractal_confirm_price": price,
                })

                if active_trend > 0 and fractal_type == "top":
                    values[index]["trend_broken"] = -1.0
                    active_trend = 0
                elif active_trend < 0 and fractal_type == "bottom":
                    values[index]["trend_broken"] = 1.0
                    active_trend = 0
                pending_trend = confirmed_pivot

                # 回归合理区间失败：离开后在区间外形成朝原脱离方向恢复的分型。
                if (
                    active_zone and departure_direction and departure_index is not None
                    and not return_failure_emitted and index - departure_index <= retest_window
                ):
                    failed_return = (
                        departure_direction > 0
                        and fractal_type == "bottom"
                        and lows[center] > active_zone.high
                    ) or (
                        departure_direction < 0
                        and fractal_type == "top"
                        and highs[center] < active_zone.low
                    )
                    if failed_return:
                        values[index]["return_failure_signal"] = float(departure_direction)
                        values[index]["signal_price"] = closes[index]
                        return_failure_emitted = True

                if not pivots:
                    pivots.append(confirmed_pivot)
                elif pivots[-1].direction == confirmed_pivot.direction:
                    more_extreme = (
                        confirmed_pivot.direction == "top" and confirmed_pivot.price > pivots[-1].price
                    ) or (
                        confirmed_pivot.direction == "bottom" and confirmed_pivot.price < pivots[-1].price
                    )
                    if more_extreme:
                        pivots[-1] = confirmed_pivot
                        if len(pivots) >= 2 and segments:
                            previous = pivots[-2]
                            start = min(previous.center_index, confirmed_pivot.center_index)
                            end = max(previous.center_index, confirmed_pivot.center_index)
                            segments[-1] = Segment(
                                start_index=start,
                                end_index=end,
                                low=min(lows[start:end + 1]),
                                high=max(highs[start:end + 1]),
                            )
                else:
                    previous = pivots[-1]
                    pivots.append(confirmed_pivot)
                    start = min(previous.center_index, confirmed_pivot.center_index)
                    end = max(previous.center_index, confirmed_pivot.center_index)
                    segments.append(Segment(
                        start_index=start,
                        end_index=end,
                        low=min(lows[start:end + 1]),
                        high=max(highs[start:end + 1]),
                    ))

                    if active_zone:
                        extension = _overlap([
                            Segment(active_zone.start_index, active_zone.confirm_index, active_zone.low, active_zone.high),
                            segments[-1],
                        ])
                        if extension:
                            active_zone.low, active_zone.high = extension
                            active_zone.fold_count += 1

                    if len(segments) >= 3:
                        candidate_segments = segments[-3:]
                        candidate = _overlap(candidate_segments)
                        if candidate and (
                            active_zone is None
                            or candidate[1] <= active_zone.low
                            or candidate[0] >= active_zone.high
                        ):
                            zone_sequence += 1
                            active_zone = ReasonableZone(
                                index=zone_sequence,
                                start_index=candidate_segments[0].start_index,
                                confirm_index=index,
                                low=candidate[0],
                                high=candidate[1],
                                fold_count=3,
                            )
                            outside_direction = 0
                            outside_count = 0
                            departure_direction = 0
                            departure_index = None
                            true_departure_emitted = False
                            return_failure_emitted = False
                            values[index]["zone_confirmed"] = 1.0

            # 分型确认后至少再有一根K线越过分型中间K线，才确认趋势。
            if pending_trend and index > pending_trend.confirm_index:
                direction = 1 if pending_trend.direction == "bottom" else -1
                extended = (
                    direction > 0 and closes[index] > highs[pending_trend.center_index]
                ) or (
                    direction < 0 and closes[index] < lows[pending_trend.center_index]
                )
                if extended:
                    active_trend = direction
                    values[index]["trend_confirmed"] = float(direction)
                    pending_trend = None
            values[index]["trend_direction"] = float(active_trend)
            values[index]["trend_intact"] = 1.0 if active_trend else 0.0

            if not active_zone:
                continue

            zone_mid = (active_zone.low + active_zone.high) / 2
            zone_age = index - active_zone.confirm_index + 1
            zone_width_pct = (active_zone.high - active_zone.low) / zone_mid * 100 if zone_mid else 0.0
            zone_mature = active_zone.fold_count >= maturity_folds or zone_age >= maturity_bars
            buffer = zone_mid * breakout_buffer_pct / 100
            direction = 1 if closes[index] > active_zone.high + buffer else -1 if closes[index] < active_zone.low - buffer else 0
            distance_pct = (
                (closes[index] - active_zone.high) / zone_mid * 100 if direction > 0
                else (closes[index] - active_zone.low) / zone_mid * 100 if direction < 0
                else 0.0
            )
            values[index].update({
                "zone_id": float(active_zone.index),
                "zone_start_time": float(times[active_zone.start_index]),
                "zone_confirm_time": float(times[active_zone.confirm_index]),
                "zone_low": active_zone.low,
                "zone_high": active_zone.high,
                "zone_mid": zone_mid,
                "zone_width_pct": zone_width_pct,
                "zone_age": float(zone_age),
                "fold_count": float(active_zone.fold_count),
                "zone_mature": 1.0 if zone_mature else 0.0,
                "inside_zone": 1.0 if direction == 0 else 0.0,
                "distance_to_zone_pct": distance_pct,
                "zone_position": float(direction),
            })

            if direction == 0:
                if departure_direction and departure_index is not None:
                    return_signal = -departure_direction
                    values[index]["zone_return_signal"] = float(return_signal)
                    values[index]["signal_price"] = closes[index]
                    if index - departure_index <= false_departure_max_bars:
                        values[index]["false_departure_signal"] = float(return_signal)
                outside_direction = 0
                outside_count = 0
                departure_direction = 0
                departure_index = None
                true_departure_emitted = False
                return_failure_emitted = False
                values[index]["zone_state"] = 1.0
                continue

            if direction == outside_direction:
                outside_count += 1
            else:
                outside_direction = direction
                outside_count = 1
                departure_direction = 0
                departure_index = None
                true_departure_emitted = False
                return_failure_emitted = False

            if not departure_direction and outside_count >= departure_confirm_bars:
                departure_direction = direction
                departure_index = index
                values[index]["zone_departure_signal"] = float(direction)
                values[index]["signal_price"] = closes[index]

            if (
                departure_direction and not true_departure_emitted
                and outside_count >= true_departure_bars
            ):
                values[index]["true_departure_signal"] = float(departure_direction)
                values[index]["signal_price"] = closes[index]
                if zone_mature:
                    values[index]["terminal_breakout_signal"] = float(departure_direction)
                true_departure_emitted = True

            values[index]["departure_direction"] = float(departure_direction or direction)
            values[index]["departure_bars"] = float(outside_count)
            values[index]["zone_state"] = 2.0 * direction

        return self._result(params, values)

    def _result(self, params: dict[str, Any], values: list[dict[str, float]]) -> IndicatorResult:
        normalized = {
            "departure_confirm_bars": int(params.get("departure_confirm_bars", 2)),
            "true_departure_bars": int(params.get("true_departure_bars", 3)),
            "false_departure_max_bars": int(params.get("false_departure_max_bars", 5)),
            "retest_window": int(params.get("retest_window", 10)),
            "maturity_bars": int(params.get("maturity_bars", 8)),
            "maturity_folds": int(params.get("maturity_folds", 4)),
            "breakout_buffer_pct": float(params.get("breakout_buffer_pct", 0.0)),
        }
        return IndicatorResult(
            type=self.type,
            params=normalized,
            values=values,
            render=RenderSpec(
                window="main",
                plots=[],
                markers=[
                    MarkerSpec(
                        field="fractal_marker", price_field="fractal_price",
                        buy_color="#56c7e8", sell_color="#f0a35a",
                        buy_label="底分型", sell_label="顶分型", size=1,
                    ),
                    MarkerSpec(
                        field="zone_return_signal", price_field="signal_price",
                        buy_color="#ff5b62", sell_color="#2fc58d",
                        buy_label="回归买", sell_label="回归卖", size=1,
                    ),
                    MarkerSpec(
                        field="return_failure_signal", price_field="signal_price",
                        buy_color="#b989f5", sell_color="#b989f5",
                        buy_label="回归失败买", sell_label="回归失败卖", size=1,
                    ),
                    MarkerSpec(
                        field="terminal_breakout_signal", price_field="signal_price",
                        buy_color="#ff6b72", sell_color="#36c995",
                        buy_label="态势脱离买", sell_label="态势脱离卖", size=1,
                    ),
                ],
            ),
        )
