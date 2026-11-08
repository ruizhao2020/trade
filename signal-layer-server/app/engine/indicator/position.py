"""位置维度：价格在近期区间中的相对位置、距高点回撤、与缠论中枢的关系。

这是「自身位置」状态的第一步——只用 K 线即可计算，不需要横截面数据。
三个输出都是逐根、因果的：

- position_pct：收盘价在最近 window 根区间（inclusive）里的分位，0=区间最低、100=区间最高；
- drawdown_pct：距最近 window 根最高价的回撤百分比，0=就在高点；
- zone_position：收盘价相对最近一个笔中枢的位置，1=中枢上方、0=中枢内、-1=中枢下方。

中枢位置复用缠论引擎（与缠论图层同一套笔/中枢口径），但只取"截至当前根"的结构，
不引入未来数据。
"""

from __future__ import annotations

from typing import Any, Optional

from app.engine.chan import ChanEngine
from app.engine.indicator.base import (
    IndicatorCalculator, IndicatorResult, RenderSpec, PlotSpec,
    _get_closes, _get_highs, _get_lows, _get_times, _param_int, register_indicator,
)


@register_indicator
class PositionCalculator(IndicatorCalculator):
    """位置：区间分位、距高点回撤、中枢位置。"""

    @property
    def type(self) -> str:
        return "position"

    def calculate(self, klines: list[dict], params: dict[str, Any]) -> IndicatorResult:
        window = _param_int(params, "window", 120)
        if not 20 <= window <= 500:
            raise ValueError("位置参考窗口应在 20 到 500 之间")

        normalized = {"window": window}
        closes = _get_closes(klines)
        highs = _get_highs(klines)
        lows = _get_lows(klines)
        times = _get_times(klines)

        values: list[dict[str, Any]] = []
        for index, timestamp in enumerate(times):
            start = max(0, index - window + 1)
            window_high = max(highs[start:index + 1])
            window_low = min(lows[start:index + 1])
            span = window_high - window_low
            close = closes[index]
            position = None if span <= 0 else round((close - window_low) / span * 100, 4)
            drawdown = None if window_high <= 0 else round((window_high - close) / window_high * 100, 4)
            values.append({
                "time": float(timestamp),
                "position_pct": position,
                "drawdown_pct": drawdown,
                "zone_position": None,
            })

        # 中枢位置：用与缠论图层一致的笔中枢口径。逐根取"起始时间不晚于当根"的
        # 最近一个中枢，判断收盘价在其上/中/下——不引用当根之后才形成的结构。
        # 用 start_time 而不是 end_time：中枢会向右延伸，end_time 会随未来数据变化，
        # 而 start_time 在形成后是稳定的（契约测试会检查前缀一致性）。
        analysis = ChanEngine().analyze(klines)
        confirmed = [
            (int(z.start_time), z.high, z.low)
            for z in analysis.zhongshus
        ]
        confirmed.sort()
        cursor = 0
        active: Optional[tuple[float, float]] = None
        for index, timestamp in enumerate(times):
            while cursor < len(confirmed) and confirmed[cursor][0] <= timestamp:
                active = (confirmed[cursor][1], confirmed[cursor][2])
                cursor += 1
            if active is None:
                continue
            close = closes[index]
            values[index]["zone_position"] = (
                1.0 if close > active[0] else (-1.0 if close < active[1] else 0.0)
            )

        render = RenderSpec(
            window="sub",
            plots=[
                PlotSpec(field="position_pct", type="line", color="#f0a35a", label="位置分位"),
                PlotSpec(field="drawdown_pct", type="line", color="#9b8cf2", label="距高点回撤%"),
            ],
        )
        return IndicatorResult(
            type=self.type, params=normalized, values=values, render=render,
        )
