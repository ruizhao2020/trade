"""把规则编译成逐根的布尔信号，以及跨级别信号对齐。"""

from __future__ import annotations

from bisect import bisect_right

from app.engine.advisor.types import LevelSeries, Rule


def _series_of(level: LevelSeries, field: str | None, key: str | None) -> list[float | None]:
    """取一条序列：key 为空表示价格序列。"""
    if key is None:
        return list(level.closes)
    return level.series(key, field or "") or []


def _at(series: list[float | None], index: int) -> float | None:
    if index < 0 or index >= len(series):
        return None
    return series[index]


def rule_signal(level: LevelSeries, rule: Rule) -> list[bool]:
    """逐根计算规则是否成立。

    None（样本不足）一律视为不成立，避免用 0 顶替产出假信号。
    """
    size = len(level.times)

    if rule.kind == "chan_point":
        marked = set(level.chan_points.get(rule.chan_point or "", []))
        return [time in marked for time in level.times]

    left = _series_of(level, rule.left_field, rule.left_key)
    right = (
        [rule.right_value] * size
        if rule.right_value is not None
        else _series_of(level, rule.right_field, rule.right_key)
    )
    if not left or not right:
        return [False] * size

    out: list[bool] = []
    for index in range(size):
        current_left = _at(left, index)
        current_right = _at(right, index)
        if current_left is None or current_right is None:
            out.append(False)
            continue

        if rule.kind == "compare":
            out.append(current_left > current_right if rule.direction == "above" else current_left < current_right)
        elif rule.kind == "direction":
            previous = _at(left, index - 1)
            if previous is None:
                out.append(False)
            else:
                out.append(current_left > previous if rule.direction == "rising" else current_left < previous)
        elif rule.kind == "cross":
            previous_left = _at(left, index - 1)
            previous_right = _at(right, index - 1)
            if previous_left is None or previous_right is None:
                out.append(False)
            elif rule.direction == "above":
                out.append(previous_left <= previous_right and current_left > current_right)
            else:
                out.append(previous_left >= previous_right and current_left < current_right)
        else:
            raise ValueError(f"未知规则类型: {rule.kind}")
    return out


def align_signal_to(primary: LevelSeries, secondary: LevelSeries, secondary_signal: list[bool]) -> list[bool]:
    """把次级级别的信号对齐到主周期的每根K线上。

    对齐口径：主周期第 i 根K线对应"次级级别中时间 <= 该K线时间"的最后一根。
    没有对应次级K线时视为不成立（该根上没有次级确认）。
    """
    if not secondary.times:
        return [False] * len(primary.times)

    aligned: list[bool] = []
    for time in primary.times:
        index = bisect_right(secondary.times, time) - 1
        if index < 0 or index >= len(secondary_signal):
            aligned.append(False)
        else:
            aligned.append(bool(secondary_signal[index]))
    return aligned


def combine(*signals: list[bool]) -> list[bool]:
    """多个信号取与（主周期触发 + 次级确认）。"""
    if not signals:
        return []
    size = min(len(item) for item in signals)
    return [all(item[index] for item in signals) for index in range(size)]
