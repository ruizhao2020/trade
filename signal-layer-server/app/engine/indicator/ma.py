from app.engine.indicator.base import (
    IndicatorCalculator, IndicatorResult, RenderSpec, PlotSpec,
    _get_closes, _get_times, _sma, register_indicator,
)
from typing import Any


@register_indicator
class MACalculator(IndicatorCalculator):
    @property
    def type(self) -> str:
        return "ma"

    def calculate(self, klines: list[dict], params: dict[str, Any]) -> IndicatorResult:
        period = int(params.get("period", 5))
        closes = _get_closes(klines)
        times = _get_times(klines)
        sma = _sma(closes, period)

        values: list[dict[str, float]] = []
        for i in range(len(times)):
            values.append({"time": float(times[i]), "value": sma[i]})

        return IndicatorResult(
            type=self.type,
            params={"period": period},
            values=values,
            render=RenderSpec(
                window="main",
                plots=[PlotSpec(field="value", type="line", color="#ffa726", label=f"MA{period}")],
            ),
        )
