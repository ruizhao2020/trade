from __future__ import annotations

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
    """成交量及相邻量柱比例分类。"""

    @property
    def type(self) -> str:
        return "volume"

    def calculate(self, klines: list[dict], params: dict[str, Any]) -> IndicatorResult:
        shrink_max = float(params.get("shrink_max", 0.8))
        increase_min = float(params.get("increase_min", 1.2))
        double_min = float(params.get("double_min", 2.0))
        triple_min = float(params.get("triple_min", 3.0))
        multiple_min = float(params.get("multiple_min", 4.0))
        if not 0 < shrink_max < increase_min < double_min < triple_min < multiple_min:
            raise ValueError("成交量阈值必须满足：0 < 缩量 < 增量 < 倍量 < 三倍量 < 多倍量")

        times = _get_times(klines)
        volumes = [max(float(item.get("volume") or 0), 0.0) for item in klines]
        values: list[dict[str, float]] = []
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
            values.append({
                "time": float(timestamp),
                "volume": volume,
                "ratio": round(ratio, 4),
                "volume_class": float(volume_class),
                "is_up": 1.0 if is_up else 0.0,
            })

        normalized_params = {
            "shrink_max": shrink_max,
            "increase_min": increase_min,
            "double_min": double_min,
            "triple_min": triple_min,
            "multiple_min": multiple_min,
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
