from __future__ import annotations

from statistics import median
from typing import Any

from app.engine.indicator.base import (
    IndicatorCalculator,
    IndicatorResult,
    PlotSpec,
    RenderSpec,
    _get_times,
    register_indicator,
)


@register_indicator
class VolumeCalculator(IndicatorCalculator):
    """成交量倍率、基础量柱形态、连续量能与相对量能。"""

    @property
    def type(self) -> str:
        return "volume"

    def calculate(self, klines: list[dict], params: dict[str, Any]) -> IndicatorResult:
        shrink_max = float(params.get("shrink_max", 0.8))
        increase_min = float(params.get("increase_min", 1.2))
        double_min = float(params.get("double_min", 2.0))
        triple_min = float(params.get("triple_min", 3.0))
        multiple_min = float(params.get("multiple_min", 4.0))
        lookback = int(params.get("lookback", 20))
        flat_tolerance = float(params.get("flat_tolerance", 0.08))
        sequence_length = int(params.get("sequence_length", 3))
        relative_period = int(params.get("relative_period", 20))
        if not 0 < shrink_max < increase_min < double_min < triple_min < multiple_min:
            raise ValueError("成交量阈值必须满足：0 < 缩量 < 增量 < 倍量 < 三倍量 < 多倍量")
        if lookback < 3 or relative_period < 2 or not 2 <= sequence_length <= 10:
            raise ValueError("量柱窗口至少为3，相对量能周期至少为2，连续根数应在2到10之间")
        if not 0 <= flat_tolerance < 0.5:
            raise ValueError("平量容差必须在0到0.5之间")

        times = _get_times(klines)
        volumes = [max(float(item.get("volume") or 0), 0.0) for item in klines]
        values: list[dict[str, float]] = []
        increase_streak = 1
        shrink_streak = 1
        for index, (timestamp, volume) in enumerate(zip(times, volumes)):
            is_up = float(klines[index].get("close", 0)) >= float(klines[index].get("open", 0))
            previous = volumes[index - 1] if index > 0 else 0.0
            ratio = volume / previous if previous > 0 else 0.0
            volume_class = 0
            if previous > 0:
                if ratio <= shrink_max:
                    volume_class = 1  # 缩量
                elif ratio >= multiple_min:
                    volume_class = 5  # 多倍量
                elif ratio >= triple_min:
                    volume_class = 4  # 三倍量
                elif ratio >= double_min:
                    volume_class = 3  # 倍量
                elif ratio >= increase_min:
                    volume_class = 2  # 增量

            if index > 0 and volume > previous:
                increase_streak += 1
            else:
                increase_streak = 1
            if index > 0 and volume < previous:
                shrink_streak += 1
            else:
                shrink_streak = 1

            window = volumes[max(0, index - lookback + 1):index + 1]
            window_ready = len(window) >= lookback and volume > 0
            has_range = window_ready and max(window) > min(window)
            is_high = has_range and volume >= max(window)
            is_low = has_range and volume <= min(window)
            is_flat = previous > 0 and abs(ratio - 1.0) <= flat_tolerance
            is_ladder = increase_streak >= sequence_length
            is_contracting = shrink_streak >= sequence_length

            # 分钟线优先使用历史同一时刻的量柱作为基线，规避开盘/午后量能节奏；
            # 样本不足时退化为普通滚动均量。
            minute_slot = (timestamp // 60_000) % (24 * 60)
            same_slot = [
                volumes[prior]
                for prior in range(index)
                if (times[prior] // 60_000) % (24 * 60) == minute_slot and volumes[prior] > 0
            ][-relative_period:]
            fallback = [item for item in volumes[max(0, index - relative_period):index] if item > 0]
            baseline_values = same_slot if len(same_slot) >= 3 else fallback
            baseline = median(baseline_values) if baseline_values else 0.0
            relative_volume = volume / baseline if baseline > 0 else 0.0

            volume_shape = 0
            if is_ladder:
                volume_shape = 4  # 梯量柱
            elif is_contracting:
                volume_shape = 5  # 连续缩量柱
            elif is_high:
                volume_shape = 1  # 高量柱
            elif is_low:
                volume_shape = 2  # 低量柱
            elif is_flat:
                volume_shape = 3  # 平量柱
            values.append({
                "time": float(timestamp),
                "volume": volume,
                "ratio": round(ratio, 4),
                "volume_class": float(volume_class),
                "volume_shape": float(volume_shape),
                "relative_volume": round(relative_volume, 4),
                "is_shrink_volume": 1.0 if previous > 0 and ratio <= shrink_max else 0.0,
                "is_increase_volume": 1.0 if previous > 0 and ratio >= increase_min else 0.0,
                "is_double_volume": 1.0 if previous > 0 and ratio >= double_min else 0.0,
                "is_triple_volume": 1.0 if previous > 0 and ratio >= triple_min else 0.0,
                "is_multiple_volume": 1.0 if previous > 0 and ratio >= multiple_min else 0.0,
                "increase_streak": float(increase_streak),
                "shrink_streak": float(shrink_streak),
                "is_high_volume": 1.0 if is_high else 0.0,
                "is_low_volume": 1.0 if is_low else 0.0,
                "is_flat_volume": 1.0 if is_flat else 0.0,
                "is_ladder_volume": 1.0 if is_ladder else 0.0,
                "is_contracting_volume": 1.0 if is_contracting else 0.0,
                "is_up": 1.0 if is_up else 0.0,
            })

        normalized_params = {
            "shrink_max": shrink_max,
            "increase_min": increase_min,
            "double_min": double_min,
            "triple_min": triple_min,
            "multiple_min": multiple_min,
            "lookback": lookback,
            "flat_tolerance": flat_tolerance,
            "sequence_length": sequence_length,
            "relative_period": relative_period,
        }
        return IndicatorResult(
            type=self.type,
            params=normalized_params,
            values=values,
            render=RenderSpec(
                window="sub",
                plots=[PlotSpec(field="volume", type="histogram", color="#596477", label="成交量")],
            ),
        )
