"""标的画像：一组独立于任何交易规则的描述量，用来解释"这个标的适合什么"。

其中缠论部分回答你举的例子：
  - 中枢破坏率：结构是否容易被打断；
  - **信号重绘率**：在更早的切片上已确认的买卖点，到后面是否还在原时间原类型上。
    重绘率高 = "结构经常被破坏"，此时缠论不可用（哪怕事后看像有赚，也可能是重绘造成的假象）；
  - 买卖点前瞻有效性：一买/二买之后的前瞻收益相对该标的中位水平的超额。
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from app.engine.chan import ChanEngine

MIN_BARS_FOR_TREND = 60
MIN_POINTS_FOR_VERDICT = 8


@dataclass
class ChanQuality:
    zhongshu_count: int = 0
    zhongshu_break_rate: float = 0.0
    point_count: int = 0
    redraw_rate: float | None = None
    forward_edge: float | None = None
    verdict: str = "数据不足"
    reasons: list[str] = field(default_factory=list)


@dataclass
class SymbolProfile:
    level: str
    bars: int
    volatility_pct: float = 0.0
    atr_pct: float = 0.0
    efficiency_ratio: float = 0.0
    gap_ratio: float = 0.0
    chan: ChanQuality = field(default_factory=ChanQuality)
    tags: list[str] = field(default_factory=list)

    def describe(self) -> str:
        parts = [
            f"波动率 {self.volatility_pct:.2f}%",
            f"ATR 占比 {self.atr_pct:.2f}%",
            f"趋势效率比 {self.efficiency_ratio:.2f}",
        ]
        if self.gap_ratio:
            parts.append(f"跳空占比 {self.gap_ratio:.1%}")
        parts.append(f"缠论适用性：{self.chan.verdict}")
        return "；".join(parts)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def basic_profile(level: str, klines: list[dict]) -> SymbolProfile:
    """不依赖缠论的基础描述量。"""
    profile = SymbolProfile(level=level, bars=len(klines))
    if len(klines) < 3:
        return profile

    closes = [float(item["close"]) for item in klines]
    highs = [float(item["high"]) for item in klines]
    lows = [float(item["low"]) for item in klines]
    opens = [float(item.get("open", item["close"])) for item in klines]

    returns = [
        (closes[index] - closes[index - 1]) / closes[index - 1] * 100
        for index in range(1, len(closes))
        if closes[index - 1] > 0
    ]
    profile.volatility_pct = round(statistics.pstdev(returns), 4) if len(returns) > 1 else 0.0

    atr_pcts = [
        (highs[index] - lows[index]) / closes[index] * 100
        for index in range(len(closes)) if closes[index] > 0
    ]
    profile.atr_pct = round(statistics.median(atr_pcts), 4) if atr_pcts else 0.0

    # 趋势效率比：净位移 / 路径总长。接近 1 = 单边趋势，接近 0 = 来回震荡。
    path = sum(abs(closes[index] - closes[index - 1]) for index in range(1, len(closes)))
    profile.efficiency_ratio = round(abs(closes[-1] - closes[0]) / path, 4) if path > 0 else 0.0

    # 跳空占比（A 股涨跌停/隔夜跳空会影响止损能否执行）
    gaps = sum(1 for index in range(1, len(closes)) if abs(opens[index] - closes[index - 1]) > 0.002 * closes[index - 1])
    profile.gap_ratio = round(gaps / (len(closes) - 1), 4)

    if len(klines) >= MIN_BARS_FOR_TREND:
        if profile.efficiency_ratio >= 0.25:
            profile.tags.append("走势偏趋势")
        elif profile.efficiency_ratio <= 0.12:
            profile.tags.append("走势偏震荡")
        if profile.atr_pct >= 3.0:
            profile.tags.append("波动剧烈")
        elif profile.atr_pct <= 1.0:
            profile.tags.append("波动温和")
    return profile


def chan_quality(
    klines: list[dict],
    *,
    redraw_checkpoints: int = 4,
    redraw_delta: int = 20,
    forward_horizon: int = 10,
) -> ChanQuality:
    """缠论结构质量：中枢破坏率、信号重绘率、买卖点前瞻有效性。"""
    quality = ChanQuality()
    if len(klines) < MIN_BARS_FOR_TREND:
        quality.reasons.append("K线数量不足，无法评估缠论结构")
        return quality

    engine = ChanEngine()
    full = engine.analyze(klines)

    zhongshus = list(full.zhongshus)
    quality.zhongshu_count = len(zhongshus)
    if zhongshus:
        broken = sum(1 for item in zhongshus if item.broken)
        quality.zhongshu_break_rate = round(broken / len(zhongshus), 4)

    points = [item for item in full.buy_sell_points if item.confirmed]
    quality.point_count = len(points)

    quality.forward_edge = _forward_edge(klines, points, forward_horizon)
    quality.redraw_rate = _redraw_rate(
        klines, engine, checkpoints=redraw_checkpoints, delta=redraw_delta,
    )

    # 结论：需要同时满足"结构稳定"和"信号有前瞻优势"
    stable = quality.redraw_rate is None or quality.redraw_rate <= 0.3
    edge = quality.forward_edge is not None and quality.forward_edge > 0

    if quality.point_count < MIN_POINTS_FOR_VERDICT:
        quality.verdict = "数据不足"
        quality.reasons.append(f"确认买卖点只有 {quality.point_count} 个，样本不足以判断")
    elif stable and edge:
        quality.verdict = "适合"
        quality.reasons.append(
            f"信号重绘率 {quality.redraw_rate:.0%} 较低且买卖点前瞻有正超额 {quality.forward_edge:.2f}%"
        )
    elif not stable:
        quality.verdict = "不适合"
        quality.reasons.append(
            f"信号重绘率 {quality.redraw_rate:.0%} 偏高，结构经常被破坏"
            if quality.redraw_rate is not None else "结构稳定性无法确认"
        )
    else:
        quality.verdict = "不适合"
        quality.reasons.append(
            f"买卖点前瞻无正超额（{quality.forward_edge:.2f}%）"
            if quality.forward_edge is not None else "买卖点前瞻有效性无法确认"
        )

    if quality.zhongshu_break_rate >= 0.8 and quality.zhongshu_count >= 3:
        quality.reasons.append(f"中枢破坏率 {quality.zhongshu_break_rate:.0%} 偏高")
    return quality


def _forward_edge(klines: list[dict], points: list, horizon: int) -> float | None:
    """买卖点之后的 H 根收益，相对该标的全部 H 根收益的均值（超额）。"""
    closes = [float(item["close"]) for item in klines]
    size = len(closes)
    if size <= horizon + 1:
        return None
    times = [int(item["open_time"]) for item in klines]
    index_of = {time: index for index, time in enumerate(times)}

    baseline_returns = [
        (closes[index + horizon] - closes[index]) / closes[index]
        for index in range(size - horizon) if closes[index] > 0
    ]
    baseline = _mean(baseline_returns)
    if not points:
        return None

    excess: list[float] = []
    for point in points:
        index = index_of.get(int(point.time))
        if index is None or index + horizon >= size or closes[index] <= 0:
            continue
        forward = (closes[index + horizon] - closes[index]) / closes[index]
        excess.append(forward - baseline)
    if not excess:
        return None
    return round(_mean(excess) * 100, 4)


def _redraw_rate(
    klines: list[dict],
    engine: ChanEngine,
    *,
    checkpoints: int,
    delta: int,
) -> float | None:
    """已确认的买卖点/背驰在后续切片里是否还留在原时间原类型上。

    重绘率 = 1 - 留存率。这个量直接对应"结构经常被破坏"。
    """
    size = len(klines)
    if size < MIN_BARS_FOR_TREND + delta + 10 or checkpoints <= 0:
        return None

    fractions = [0.55, 0.7, 0.85, 0.95][:checkpoints]
    total = 0
    persisted = 0
    for fraction in fractions:
        cut = int(size * fraction)
        if cut + delta > size or cut < MIN_BARS_FOR_TREND:
            continue
        early = engine.analyze(klines[:cut])
        later = engine.analyze(klines[: cut + delta])
        later_keys = {
            ("point", item.type, int(item.time))
            for item in later.buy_sell_points if item.confirmed
        } | {
            ("div", item.type, int(item.time))
            for item in later.divergences if item.confirmed
        }
        for item in early.buy_sell_points:
            if not item.confirmed:
                continue
            total += 1
            if ("point", item.type, int(item.time)) in later_keys:
                persisted += 1
        for item in early.divergences:
            if not item.confirmed:
                continue
            total += 1
            if ("div", item.type, int(item.time)) in later_keys:
                persisted += 1

    if total == 0:
        return None
    return round(1 - persisted / total, 4)
