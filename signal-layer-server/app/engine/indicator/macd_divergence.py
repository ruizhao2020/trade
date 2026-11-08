"""MACD 柱群背驰：用相邻同色柱群的面积对比识别顶背驰与底背驰。

缠论用 MACD 辅助判断背驰：价格创了新高（或新低），但对应的红柱群（绿柱群）
面积反而比前一群小，说明推动力在衰减。

## 口径

- 红柱群 = `histogram > 0` 的连续段，绿柱群 = `histogram < 0` 的连续段；
  `0` 与预热期的 `None` 都断开一段。
- 顶背驰：相邻两个红柱群（中间隔一个绿柱群），前群面积 > 后群面积，
  且后群覆盖的 K 线最高价 > 前群覆盖的最高价。
- 底背驰：对称，前群面积 > 后群面积，且后群最低价 < 前群最低价。
- 信号落在第二个柱群结束后的第一根：那时后群的面积才定型。
  把信号落在群内或群尾都会用到未来数据，会在回测里变成前视。

面积用 `Σ|histogram|`，与缠论"看红柱/绿柱面积"的说法一致；峰位取群内
`histogram` 的极值，只用于画箭头的端点。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass
class HistCluster:
    """一段同色柱群。"""

    color: int          # 1 = 红柱群（histogram > 0），-1 = 绿柱群
    start: int          # 首根下标
    end: int            # 末根下标（含）
    area: float         # 面积 Σ|histogram|
    peak_index: int     # 峰位下标（红群取最大，绿群取最小）
    peak_value: float   # 峰值
    high: float         # 群内最高价
    low: float          # 群内最低价

    @property
    def bars(self) -> int:
        return self.end - self.start + 1


@dataclass
class MacdDivergence:
    """一次确认的 MACD 柱群背驰。"""

    kind: Literal["top", "bottom"]
    confirm_index: int      # 信号落点：后一群结束后的第一根
    from_index: int         # 前群峰位下标
    from_value: float
    to_index: int           # 后群峰位下标
    to_value: float
    reference_area: float   # 前群面积
    current_area: float     # 后群面积

    @property
    def strength_ratio(self) -> float:
        if self.reference_area <= 0:
            return 0.0
        return self.current_area / self.reference_area


def _build_clusters(
    hist: list[float | None], highs: list[float], lows: list[float],
) -> list[HistCluster]:
    """把柱体序列切成同色连续段。颜色交替出现，峰位是群内极值。"""
    clusters: list[HistCluster] = []
    index = 0
    count = len(hist)
    while index < count:
        value = hist[index]
        if value is None or value == 0:
            index += 1
            continue
        color = 1 if value > 0 else -1
        end = index
        while end + 1 < count:
            nxt = hist[end + 1]
            if nxt is None or nxt * color <= 0:
                break
            end += 1
        segment = [float(hist[pos]) for pos in range(index, end + 1)]
        area = sum(abs(item) for item in segment)
        if color > 0:
            offset = max(range(len(segment)), key=lambda pos: segment[pos])
        else:
            offset = min(range(len(segment)), key=lambda pos: segment[pos])
        peak_index = index + offset
        clusters.append(HistCluster(
            color=color,
            start=index,
            end=end,
            area=area,
            peak_index=peak_index,
            peak_value=segment[offset],
            high=max(highs[index:end + 1]),
            low=min(lows[index:end + 1]),
        ))
        index = end + 1
    return clusters


def detect_macd_divergences(
    hist: list[float | None],
    highs: list[float],
    lows: list[float],
    min_bars: int = 3,
) -> list[MacdDivergence]:
    """识别相邻同色柱群的背驰。``min_bars`` 过滤过短的柱群（噪声）。"""
    if min_bars < 1:
        raise ValueError("柱群最少根数应大于等于1")
    if len(hist) != len(highs) or len(hist) != len(lows):
        raise ValueError("柱体与 K 线序列长度不一致")

    clusters = _build_clusters(hist, highs, lows)
    results: list[MacdDivergence] = []

    # 柱群颜色交替（红、绿、红...），所以同一颜色的相邻两群相隔一个下标。
    for position in range(len(clusters) - 2):
        previous = clusters[position]
        current = clusters[position + 2]
        if previous.color != current.color:
            continue
        if previous.bars < min_bars or current.bars < min_bars:
            continue
        # 后一群必须已经收完：收完的下一根才能确认面积，避免前视
        confirm_index = current.end + 1
        if confirm_index >= len(hist):
            continue
        if previous.area <= current.area:
            continue
        if current.color > 0:
            if current.high <= previous.high:
                continue
            kind: Literal["top", "bottom"] = "top"
        else:
            if current.low >= previous.low:
                continue
            kind = "bottom"
        results.append(MacdDivergence(
            kind=kind,
            confirm_index=confirm_index,
            from_index=previous.peak_index,
            from_value=previous.peak_value,
            to_index=current.peak_index,
            to_value=current.peak_value,
            reference_area=previous.area,
            current_area=current.area,
        ))
    return results
