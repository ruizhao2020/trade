from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class TimeRange:
    start: int
    end: int

    def __post_init__(self):
        if self.start > self.end:
            raise ValueError("start_time must be less than or equal to end_time")


def merge_ranges(ranges: list[TimeRange]) -> list[TimeRange]:
    if not ranges:
        return []
    merged = [sorted(ranges)[0]]
    for current in sorted(ranges)[1:]:
        previous = merged[-1]
        if current.start <= previous.end + 1:
            merged[-1] = TimeRange(previous.start, max(previous.end, current.end))
        else:
            merged.append(current)
    return merged


def missing_ranges(requested: TimeRange, covered: list[TimeRange]) -> list[TimeRange]:
    """从请求区间中减去已经确认覆盖的区间。"""
    missing: list[TimeRange] = []
    cursor = requested.start
    for item in merge_ranges(covered):
        if item.end < cursor or item.start > requested.end:
            continue
        if item.start > cursor:
            missing.append(TimeRange(cursor, min(item.start - 1, requested.end)))
        cursor = max(cursor, item.end + 1)
        if cursor > requested.end:
            break
    if cursor <= requested.end:
        missing.append(TimeRange(cursor, requested.end))
    return missing


def infer_coverage(timestamps: list[int], timeframe: str) -> list[TimeRange]:
    """为没有覆盖元数据的旧表推断连续数据簇。

    日线允许春节等长假；分钟线允许隔夜、周末和短假。超过阈值才视为真实缺口。
    """
    points = sorted(set(timestamps))
    if not points:
        return []
    max_gap = 14 * 24 * 60 * 60 * 1000 if timeframe == "1d" else 4 * 24 * 60 * 60 * 1000
    ranges: list[TimeRange] = []
    start = previous = points[0]
    for point in points[1:]:
        if point - previous > max_gap:
            ranges.append(TimeRange(start, previous))
            start = point
        previous = point
    ranges.append(TimeRange(start, previous))
    return ranges
