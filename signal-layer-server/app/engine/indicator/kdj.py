from app.engine.indicator.base import (
    IndicatorCalculator, IndicatorResult, RenderSpec, PlotSpec,
    _get_closes, _get_highs, _get_lows, _get_times, register_indicator,
)
from typing import Any


@register_indicator
class KDJCalculator(IndicatorCalculator):
    @property
    def type(self) -> str:
        return "kdj"

    def calculate(self, klines: list[dict], params: dict[str, Any]) -> IndicatorResult:
        n = int(params.get("n", 9))
        m1 = int(params.get("m1", 3))
        m2 = int(params.get("m2", 3))

        closes = _get_closes(klines)
        highs = _get_highs(klines)
        lows = _get_lows(klines)
        times = _get_times(klines)

        render = RenderSpec(
            window="sub",
            plots=[
                PlotSpec(field="k", type="line", color="#ffa726", label="K"),
                PlotSpec(field="d", type="line", color="#42a5f5", label="D"),
                PlotSpec(field="j", type="line", color="#ef5350", label="J"),
            ],
        )

        if len(closes) < n:
            return IndicatorResult(
                type=self.type, params={"n": n, "m1": m1, "m2": m2},
                values=[], render=render,
            )

        k_values: list[float] = [50.0] * n
        d_values: list[float] = [50.0] * n
        j_values: list[float] = [50.0] * n

        for i in range(n, len(closes)):
            window_high = max(highs[i - n + 1:i + 1])
            window_low = min(lows[i - n + 1:i + 1])
            c = closes[i]

            rsv = 50.0
            if window_high != window_low:
                rsv = (c - window_low) / (window_high - window_low) * 100.0

            k = (2.0 / 3.0) * k_values[-1] + (1.0 / 3.0) * rsv
            d = (2.0 / 3.0) * d_values[-1] + (1.0 / 3.0) * k
            j = 3.0 * k - 2.0 * d

            k_values.append(k)
            d_values.append(d)
            j_values.append(j)

        values: list[dict[str, float]] = []
        for i in range(n - 1):
            values.append({
                "time": float(times[i]),
                "k": k_values[i],
                "d": d_values[i],
                "j": j_values[i],
            })

        for i in range(n - 1, len(times)):
            values.append({
                "time": float(times[i]),
                "k": round(k_values[i], 4),
                "d": round(d_values[i], 4),
                "j": round(j_values[i], 4),
            })

        return IndicatorResult(
            type=self.type,
            params={"n": n, "m1": m1, "m2": m2},
            values=values,
            render=render,
        )
