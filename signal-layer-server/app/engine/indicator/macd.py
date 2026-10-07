from __future__ import annotations

from typing import Any, Optional

from app.engine.indicator.base import (
    IndicatorCalculator, IndicatorResult, RenderSpec, PlotSpec,
    _ema, _get_closes, _get_times, _param_int, register_indicator,
)


@register_indicator
class MACDCalculator(IndicatorCalculator):
    """MACD（TA-Lib / Pine 口径）。

    输出与 K 线逐根对齐，预热期 None：
    - DIF 从第 `slow-1` 根起有效（快慢线都要有值）
    - DEA 从第 `slow+signal-2` 根起有效（DEA 是 DIF 的均线，要再多 signal-1 根）
    - 三者未定义时为 None，不填 0

    修复前：`_ema` 用首值播种且不返回 None，于是第 0 根的 DIF/DEA/柱体全是 0。
    那不是行情决定的读数，却会被"柱体转正"这类条件当成真实信号。
    """

    @property
    def type(self) -> str:
        return "macd"

    def calculate(self, klines: list[dict], params: dict[str, Any]) -> IndicatorResult:
        fast = _param_int(params, "fast", 12)
        slow = _param_int(params, "slow", 26)
        signal = _param_int(params, "signal", 9)
        if not 1 <= fast < slow <= 200:
            raise ValueError("MACD 快线周期应大于等于1且小于慢线，慢线不超过200")
        if not 1 <= signal <= 200:
            raise ValueError("MACD 信号线周期应在 1 到 200 之间")

        normalized = {"fast": fast, "slow": slow, "signal": signal}
        closes = _get_closes(klines)
        times = _get_times(klines)
        render = RenderSpec(
            window="sub",
            plots=[
                PlotSpec(field="dif", type="line", color="#26a69a", label="DIF"),
                PlotSpec(field="dea", type="line", color="#ef5350", label="DEA"),
                PlotSpec(field="histogram", type="histogram", color="#888", label="MACD"),
            ],
        )

        ema_fast = _ema(closes, fast)
        ema_slow = _ema(closes, slow)

        difs: list[Optional[float]] = []
        for index in range(len(closes)):
            fast_value = ema_fast[index]
            slow_value = ema_slow[index]
            # 任一均线未定义则 DIF 未定义，不能拿 0 顶上
            if fast_value is None or slow_value is None:
                difs.append(None)
                continue
            difs.append(fast_value - slow_value)

        deas = _ema(difs, signal)

        values: list[dict[str, Any]] = []
        for index, timestamp in enumerate(times):
            dif = difs[index]
            dea = deas[index]
            values.append({
                "time": float(timestamp),
                "dif": None if dif is None else round(dif, 8),
                "dea": None if dea is None else round(dea, 8),
                "histogram": None if (dif is None or dea is None) else round(dif - dea, 8),
            })

        return IndicatorResult(
            type=self.type, params=normalized, values=values, render=render,
        )
