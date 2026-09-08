from app.engine.indicator.base import (
    IndicatorCalculator, IndicatorResult, RenderSpec, PlotSpec,
    _get_closes, _get_times, register_indicator,
)
from typing import Any


@register_indicator
class RSICalculator(IndicatorCalculator):
    @property
    def type(self) -> str:
        return "rsi"

    def calculate(self, klines: list[dict], params: dict[str, Any]) -> IndicatorResult:
        period = int(params.get("period", 14))
        closes = _get_closes(klines)
        times = _get_times(klines)

        render = RenderSpec(
            window="sub",
            plots=[PlotSpec(field="value", type="line", color="#ab47bc", label=f"RSI{period}")],
        )

        if len(closes) < period + 1:
            return IndicatorResult(
                type=self.type, params={"period": period}, values=[], render=render,
            )

        gains: list[float] = []
        losses: list[float] = []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i - 1]
            gains.append(max(diff, 0.0))
            losses.append(max(-diff, 0.0))

        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        values: list[dict[str, float]] = [{"time": float(times[0]), "value": 50.0}]

        for i in range(period, len(gains)):
            if avg_loss == 0:
                rsi = 100.0
            else:
                rs = avg_gain / avg_loss
                rsi = 100.0 - (100.0 / (1.0 + rs))

            values.append({"time": float(times[i + 1]), "value": round(rsi, 4)})

            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        return IndicatorResult(type=self.type, params={"period": period}, values=values, render=render)
