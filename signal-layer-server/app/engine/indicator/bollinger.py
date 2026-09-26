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

        upper: list[float | None] = []
        middle: list[float | None] = []
        lower: list[float | None] = []

        for i in range(len(closes)):
            # 样本不足 period 根时中轨与上下轨都无意义，输出 None 让前端断线
            if i < period - 1:
                upper.append(None)
                middle.append(None)
                lower.append(None)
                continue

            window = closes[i - period + 1:i + 1]
            mean = sma[i]
            variance = sum((x - mean) ** 2 for x in window) / period
            std = sqrt(variance)

            band_diff = std_dev * std
            upper.append(mean + band_diff)
            middle.append(mean)
            lower.append(mean - band_diff)

        values: list[dict[str, Any]] = []
        for i in range(len(times)):
            values.append({
                "time": float(times[i]),
                "upper": None if upper[i] is None else round(upper[i], 8),
                "middle": None if middle[i] is None else round(middle[i], 8),
                "lower": None if lower[i] is None else round(lower[i], 8),
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
