from app.engine.indicator.base import (
    IndicatorCalculator, IndicatorResult, RenderSpec, PlotSpec,
    _get_closes, _get_times, _ema, register_indicator,
)
from typing import Any


@register_indicator
class MACDCalculator(IndicatorCalculator):
    @property
    def type(self) -> str:
        return "macd"

    def calculate(self, klines: list[dict], params: dict[str, Any]) -> IndicatorResult:
        fast = int(params.get("fast", 12))
        slow = int(params.get("slow", 26))
        signal = int(params.get("signal", 9))

        closes = _get_closes(klines)
        times = _get_times(klines)

        if len(closes) < slow:
            return IndicatorResult(
                type=self.type,
                params={"fast": fast, "slow": slow, "signal": signal},
                values=[],
                render=RenderSpec(
                    window="sub",
                    plots=[
                        PlotSpec(field="dif", type="line", color="#26a69a", label="DIF"),
                        PlotSpec(field="dea", type="line", color="#ef5350", label="DEA"),
                        PlotSpec(field="histogram", type="histogram", color="#888", label="MACD"),
                    ],
                ),
            )

        ema_fast = _ema(closes, fast)
        ema_slow = _ema(closes, slow)

        difs: list[float] = []
        for i in range(len(closes)):
            difs.append(ema_fast[i] - ema_slow[i])

        deas = _ema(difs, signal)

        values: list[dict[str, float]] = []
        for i in range(len(times)):
            histogram = difs[i] - deas[i]
            values.append({
                "time": float(times[i]),
                "dif": round(difs[i], 8),
                "dea": round(deas[i], 8),
                "histogram": round(histogram, 8),
            })

        return IndicatorResult(
            type=self.type,
            params={"fast": fast, "slow": slow, "signal": signal},
            values=values,
            render=RenderSpec(
                window="sub",
                plots=[
                    PlotSpec(field="dif", type="line", color="#26a69a", label="DIF"),
                    PlotSpec(field="dea", type="line", color="#ef5350", label="DEA"),
                    PlotSpec(field="histogram", type="histogram", color="#888", label="MACD"),
                ],
            ),
        )
