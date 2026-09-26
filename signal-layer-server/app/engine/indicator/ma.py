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
        touch_tolerance_pct = float(params.get("touch_tolerance_pct", 0.5))
        if period < 1 or not 0 <= touch_tolerance_pct <= 10:
            raise ValueError("均线周期必须大于0，支撑压制容差应在0到10之间")
        closes = _get_closes(klines)
        times = _get_times(klines)
        sma = _sma(closes, period)

        values: list[dict[str, Any]] = []
        for i in range(len(times)):
            ma = sma[i]
            # 样本不足 period 根时不产生均线值，前端据此断线（不与收盘价重合）
            if ma is None:
                values.append({
                    "time": float(times[i]),
                    "value": None,
                    "support": 0.0,
                    "resistance": 0.0,
                })
                continue
            open_price = float(klines[i].get("open", closes[i]))
            high = float(klines[i].get("high", closes[i]))
            low = float(klines[i].get("low", closes[i]))
            tolerance = abs(ma) * touch_tolerance_pct / 100
            support = low <= ma + tolerance and closes[i] >= ma and closes[i] >= open_price
            resistance = high >= ma - tolerance and closes[i] <= ma and closes[i] <= open_price
            values.append({
                "time": float(times[i]),
                "value": ma,
                "support": 1.0 if support else 0.0,
                "resistance": 1.0 if resistance else 0.0,
            })

        return IndicatorResult(
            type=self.type,
            params={"period": period, "touch_tolerance_pct": touch_tolerance_pct},
            values=values,
            render=RenderSpec(
                window="main",
                plots=[PlotSpec(field="value", type="line", color="#ffa726", label=f"MA{period}")],
            ),
        )
