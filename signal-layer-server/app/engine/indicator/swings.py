"""摆动高低点（±N 根枢轴）。

支撑压力位与流动性聚集区都要先找出"走势的转折点"，因此把这层抽出来共用，
避免两个指标各写一套枢轴检测再互相打架。

为什么不用缠论的分型：缠论分型（`chan/fenxing.py`）是 3 根 K 线的严格分型，
并且额外受"顶底交替、与笔的成立条件"约束。那是缠论体系内部的规则，
拿来做支撑压力位会让 S/R 的取值随缠论实现变化而漂移。这里用的是行业共识的
±N 根枢轴（TradingView `ta.pivothigh/pivotlow` 的同口径），窗口宽度可调。

平局处理：平头（连续等高的高点）只取最左那一根，规则是"必须严格高于前一根"。
不做这个约束的话，一字平台上的每一根都会被记成枢轴，同一个顶部被计数多次，
直接虚增支撑压力位的"触碰次数"。
"""

from __future__ import annotations


def swing_pivots(
    highs: list[float], lows: list[float], span: int,
) -> tuple[dict[int, float], dict[int, float]]:
    """找出所有摆动高点与摆动低点。

    Args:
        highs / lows: 最高价、最低价序列
        span: 左右各看多少根。枢轴位于 p 时，需要 [p-span, p+span] 这个窗口，
              因此它要到第 p+span 根才能被确认。

    Returns:
        (枢轴高点 {bar: price}, 枢轴低点 {bar: price})，按 bar 升序。
        价格取枢轴那根自身的 high / low。
    """
    if span < 1:
        raise ValueError("摆动点窗口至少为1")

    highs_pivots: dict[int, float] = {}
    lows_pivots: dict[int, float] = {}
    for center in range(span, len(highs) - span):
        window_high = max(highs[center - span:center + span + 1])
        window_low = min(lows[center - span:center + span + 1])
        # `> highs[center-1]` 是左严格平局规则；center >= span >= 1 保证下标有效
        if highs[center] >= window_high and highs[center] > highs[center - 1]:
            highs_pivots[center] = highs[center]
        if lows[center] <= window_low and lows[center] < lows[center - 1]:
            lows_pivots[center] = lows[center]
    return highs_pivots, lows_pivots
