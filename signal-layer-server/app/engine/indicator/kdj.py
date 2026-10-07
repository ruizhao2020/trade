from __future__ import annotations

from typing import Any, Optional

from app.engine.indicator.base import (
    IndicatorCalculator, IndicatorResult, RenderSpec, PlotSpec,
    _get_closes, _get_highs, _get_lows, _get_times, _param_int, register_indicator,
)


@register_indicator
class KDJCalculator(IndicatorCalculator):
    """KDJ（通达信口径）。

    RSV 需要 n 根窗口，因此第 `n-1` 根就有第一个可用的 RSV；
    K/D 以 50 为初值按 m1/m2 递推，J = 3K - 2D。
    预热期(第 0..n-2 根)K/D/J 为 None。

    修复前的两个问题：
    - `m1`/`m2` 读了却没用（平滑系数写死 2/3、1/3），改参数输出不变；
    - 循环从第 n 根才开始，于是第 n-1 根明明能算出 RSV，却被填成种子 50。
    """

    @property
    def type(self) -> str:
        return "kdj"

    def calculate(self, klines: list[dict], params: dict[str, Any]) -> IndicatorResult:
        n = _param_int(params, "n", 9)
        m1 = _param_int(params, "m1", 3)
        m2 = _param_int(params, "m2", 3)
        if not 2 <= n <= 200:
            raise ValueError("KDJ 的 n 应在 2 到 200 之间")
        if not 1 <= m1 <= 100 or not 1 <= m2 <= 100:
            raise ValueError("KDJ 的 m1/m2 应在 1 到 100 之间")

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

        k_values: list[Optional[float]] = [None] * len(closes)
        d_values: list[Optional[float]] = [None] * len(closes)
        j_values: list[Optional[float]] = [None] * len(closes)

        previous_k = 50.0
        previous_d = 50.0
        for index in range(n - 1, len(closes)):
            window_high = max(highs[index - n + 1:index + 1])
            window_low = min(lows[index - n + 1:index + 1])
            # 窗口内最高等于最低（一字板等）时 RSV 无定义，按惯例取 50
            rsv = 50.0 if window_high == window_low else (
                (closes[index] - window_low) / (window_high - window_low) * 100.0
            )
            k = ((m1 - 1) * previous_k + rsv) / m1
            d = ((m2 - 1) * previous_d + k) / m2
            k_values[index] = k
            d_values[index] = d
            j_values[index] = 3.0 * k - 2.0 * d
            previous_k = k
            previous_d = d

        values: list[dict[str, Any]] = []
        for index, timestamp in enumerate(times):
            if k_values[index] is None:
                values.append({"time": float(timestamp), "k": None, "d": None, "j": None})
                continue
            values.append({
                "time": float(timestamp),
                "k": round(k_values[index], 4),
                "d": round(d_values[index], 4),
                "j": round(j_values[index], 4),
            })

        return IndicatorResult(
            type=self.type,
            params={"n": n, "m1": m1, "m2": m2},
            values=values,
            render=render,
        )
