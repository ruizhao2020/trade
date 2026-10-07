from __future__ import annotations

from typing import Any, Optional

from app.engine.indicator.base import (
    IndicatorCalculator, IndicatorResult, RenderSpec, PlotSpec,
    _get_closes, _get_times, _param_int, _rma, register_indicator,
)


@register_indicator
class RSICalculator(IndicatorCalculator):
    """Wilder RSI。

    输出与 K 线逐根对齐(长度相同)，预热期 None：
    第 i 根的值 = 截至第 i 根收盘的 RSI。

    修复前的实现有两处错位：values 比 klines 短 period 行(第 1..period 根
    完全没有行)，且每个值被贴到了后一根上——即图上整条线左移一格、
    条件判断实际读到的是前一根的 RSI。
    """

    @property
    def type(self) -> str:
        return "rsi"

    def calculate(self, klines: list[dict], params: dict[str, Any]) -> IndicatorResult:
        period = _param_int(params, "period", 14)
        if not 2 <= period <= 200:
            raise ValueError("RSI 周期应在 2 到 200 之间")

        closes = _get_closes(klines)
        times = _get_times(klines)
        render = RenderSpec(
            window="sub",
            plots=[PlotSpec(field="value", type="line", color="#ab47bc", label=f"RSI{period}")],
        )

        # 每根 K 线的涨跌幅：第 0 根无前收，记为 None。
        gains: list[Optional[float]] = [None]
        losses: list[Optional[float]] = [None]
        for index in range(1, len(closes)):
            change = closes[index] - closes[index - 1]
            gains.append(max(change, 0.0))
            losses.append(max(-change, 0.0))

        avg_gain = _rma(gains, period)
        avg_loss = _rma(losses, period)

        values: list[dict[str, Any]] = []
        for index, timestamp in enumerate(times):
            gain = avg_gain[index]
            loss = avg_loss[index]
            if gain is None or loss is None:
                values.append({"time": float(timestamp), "value": None})
                continue
            if loss == 0:
                # 全程无下跌：RSI 定义为 100（有涨无跌），不是 0 也不是未定义
                rsi = 100.0
            else:
                rs = gain / loss
                rsi = 100.0 - 100.0 / (1.0 + rs)
            values.append({"time": float(timestamp), "value": round(rsi, 4)})

        return IndicatorResult(
            type=self.type, params={"period": period}, values=values, render=render,
        )
