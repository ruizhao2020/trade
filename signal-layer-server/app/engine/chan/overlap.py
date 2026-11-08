"""K 线重叠级别（零缠体系的"K 线重叠理论"）。

在观察的级别图上，连续 K 线的高低点如果有公共交集，说明这些小级别走势在更大的
级别上重叠成了一个中枢。这里只做**展示用的级别参考**：不参与笔、中枢、买卖点
判定，改它不会影响任何策略结果。

判定方式：从一根 K 线起不断并入下一根，公共区间 = [max(low), min(high)]；
交集一旦为空就结束一段，从下一根重新开始。按段内 K 线根数分档（经验阈值）：

- 18 根及以上 ≈ 次级别中枢
- 5–17 根 ≈ 次次级别中枢
- 3–4 根 ≈ 过渡区（材料里的"空白区"）

这套分档来自零缠的二手整理稿，不是严格推导，阈值全部可调、可被后续数据校准。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SUB_LEVEL_LABELS: dict[str, str] = {
    "sub1": "次级别",
    "sub2": "次次级别",
    "sub3": "过渡区",
}

SUB_LEVEL_MIN_BARS: dict[str, int] = {"sub1": 18, "sub2": 5, "sub3": 3}


@dataclass
class KlineOverlap:
    """一段连续 K 线的公共重叠区间。"""

    start_index: int
    end_index: int          # 含
    start_time: int
    end_time: int
    low: float              # 公共区间下沿 = 段内 max(low)
    high: float             # 公共区间上沿 = 段内 min(high)
    bars: int
    level: Literal["sub1", "sub2", "sub3"]

    @property
    def label(self) -> str:
        return SUB_LEVEL_LABELS[self.level]


def _level_for(bars: int) -> Literal["sub1", "sub2", "sub3"] | None:
    if bars >= SUB_LEVEL_MIN_BARS["sub1"]:
        return "sub1"
    if bars >= SUB_LEVEL_MIN_BARS["sub2"]:
        return "sub2"
    if bars >= SUB_LEVEL_MIN_BARS["sub3"]:
        return "sub3"
    return None


def detect_kline_overlaps(klines: list[dict], min_bars: int = 3) -> list[KlineOverlap]:
    """找出所有满足最小根数的重叠段，按时间顺序返回。"""
    if not klines:
        return []
    result: list[KlineOverlap] = []
    index = 0
    total = len(klines)
    while index < total:
        low = float(klines[index]["low"])
        high = float(klines[index]["high"])
        end = index
        while end + 1 < total:
            next_low = max(low, float(klines[end + 1]["low"]))
            next_high = min(high, float(klines[end + 1]["high"]))
            if next_low > next_high:
                break
            low, high = next_low, next_high
            end += 1
        bars = end - index + 1
        level = _level_for(bars) if bars >= min_bars else None
        if level is not None:
            result.append(KlineOverlap(
                start_index=index,
                end_index=end,
                start_time=int(klines[index]["open_time"]),
                end_time=int(klines[end]["open_time"]),
                low=round(low, 4),
                high=round(high, 4),
                bars=bars,
                level=level,
            ))
        index = end + 1
    return result
