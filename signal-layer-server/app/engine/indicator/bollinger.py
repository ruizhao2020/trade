from math import sqrt
from app.engine.indicator.base import (
    IndicatorCalculator, IndicatorResult, RenderSpec, PlotSpec,
    _get_closes, _get_times, _sma, register_indicator,
)
from typing import Any


@register_indicator
class BollingerCalculator(IndicatorCalculator):
    @property
    def type(self) -> str:
        return "bollinger"

    def calculate(self, klines: list[dict], params: dict[str, Any]) -> IndicatorResult:
        period = int(params.get("period", 20))
        std_dev = float(params.get("std", 2.0))

        closes = _get_closes(klines)
        times = _get_times(klines)

        sma = _sma(closes, period)

        upper: list[float] = []
        middle: list[float] = []
        lower: list[float] = []

        for i in range(len(closes)):
            if i < period - 1:
                mid = closes[i]
                upper.append(mid)
                middle.append(mid)
                lower.append(mid)
                continue

            window = closes[i - period + 1:i + 1]
            mean = sma[i]
            variance = sum((x - mean) ** 2 for x in window) / period
            std = sqrt(variance)

            band_diff = std_dev * std
            upper.append(mean + band_diff)
            middle.append(mean)
            lower.append(mean - band_diff)

        values: list[dict[str, float]] = []
        for i in range(len(times)):
            values.append({
                "time": float(times[i]),
                "upper": round(upper[i], 8),
                "middle": round(middle[i], 8),
                "lower": round(lower[i], 8),
            })

        return IndicatorResult(
            type=self.type,
            params={"period": period, "std": std_dev},
            values=values,
            render=RenderSpec(
                window="main",
                plots=[
                    PlotSpec(field="upper", type="line", color="#7e57c2", label="UP"),
                    PlotSpec(field="middle", type="line", color="#ffa726", label="MID"),
                    PlotSpec(field="lower", type="line", color="#7e57c2", label="LOW"),
                ],
            ),
        )
