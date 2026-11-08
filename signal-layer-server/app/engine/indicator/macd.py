from __future__ import annotations

from typing import Any, Optional

from app.engine.indicator.base import (
    ArrowSpec, IndicatorCalculator, IndicatorResult, RenderSpec, PlotSpec,
    _ema, _get_closes, _get_highs, _get_lows, _get_times, _param_int, register_indicator,
)
from app.engine.indicator.macd_divergence import detect_macd_divergences


@register_indicator
class MACDCalculator(IndicatorCalculator):
    """MACD（TA-Lib / Pine 口径），附带柱群背驰标注。

    输出与 K 线逐根对齐，预热期 None：
    - DIF 从第 `slow-1` 根起有效（快慢线都要有值）
    - DEA 从第 `slow+signal-2` 根起有效（DEA 是 DIF 的均线，要再多 signal-1 根）
    - 三者未定义时为 None，不填 0

    修复前：`_ema` 用首值播种且不返回 None，于是第 0 根的 DIF/DEA/柱体全是 0。
    那不是行情决定的读数，却会被"柱体转正"这类条件当成真实信号。

    背驰（见 macd_divergence.py）：相邻两个红柱群（或绿柱群）里，前群面积更大，
    价格却创了新高（新低），就是顶背驰（底背驰）。信号落在后一群收完的下一根，
    箭头则连接两群的峰位，供副图绘制。
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
        min_bars = _param_int(params, "divergence_min_bars", 3)
        if min_bars < 1:
            raise ValueError("柱群最少根数应大于等于1")

        normalized = {
            "fast": fast, "slow": slow, "signal": signal,
            "divergence_min_bars": min_bars,
        }
        closes = _get_closes(klines)
        highs = _get_highs(klines)
        lows = _get_lows(klines)
        times = _get_times(klines)

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
            histogram = None if (dif is None or dea is None) else round(dif - dea, 8)
            values.append({
                "time": float(timestamp),
                "dif": None if dif is None else round(dif, 8),
                "dea": None if dea is None else round(dea, 8),
                "histogram": histogram,
                # 事件字段：0 = 当根不成立；预热期没有柱体，保持 None
                "top_divergence": None if histogram is None else 0.0,
                "bottom_divergence": None if histogram is None else 0.0,
            })

        divergences = detect_macd_divergences(
            [row["histogram"] for row in values], highs, lows, min_bars,
        )
        for item in divergences:
            row = values[item.confirm_index]
            if item.kind == "top":
                row["top_divergence"] = 1.0
            else:
                row["bottom_divergence"] = 1.0

        render = RenderSpec(
            window="sub",
            plots=[
                PlotSpec(field="dif", type="line", color="#26a69a", label="DIF"),
                PlotSpec(field="dea", type="line", color="#ef5350", label="DEA"),
                # 红柱/绿柱按柱体正负分色，和缠论里"红柱群/绿柱群"的说法对应
                PlotSpec(
                    field="histogram", type="histogram",
                    color="#ff5b62", negative_color="#2fc58d", label="MACD",
                ),
            ],
            arrows=[
                ArrowSpec(
                    from_time=times[item.from_index],
                    from_value=round(item.from_value, 8),
                    to_time=times[item.to_index],
                    to_value=round(item.to_value, 8),
                    direction=item.kind,
                    color="#ff5b62" if item.kind == "top" else "#2fc58d",
                )
                for item in divergences
            ],
        )

        return IndicatorResult(
            type=self.type, params=normalized, values=values, render=render,
        )
