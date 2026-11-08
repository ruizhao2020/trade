"""指标字段有效性评测：前瞻收益的事件研究 + 规则扫描。

评测单元是"字段"，不是"指标"：同一指标的不同输出字段（量价齐升 vs 放量滞涨）
有效性可以完全相反。

## 口径

- 事件在第 i 根收盘确认，第 i+1 根收盘入场，持有 horizon 根后按收盘计算收益。
  不用事件当根收盘成交，避免"收盘才知道、收盘就成交"。
- 成本按一次完整往返扣减（佣金+印花税+滑点），默认 0.2%。
- 同向事件在持有期内不重复计数（同一段行情只算一次）。
- 基线＝同一批标的、同一持有期、所有可入场点的平均前瞻收益。
- 显著性用随机化检验：每个标的里随机抽与事件同样多的入场点，重复若干次，
  看事件组净收益在随机分布里的位置。这样能自然吸收事件聚集与市场整体漂移。
- 多重检验：规则扫描的 p 值按候选规则数做 Bonferroni 校正。

结论带作用域：换周期、换股票池、换持有期，结论可能完全不同。
"""

from __future__ import annotations

import random
import zlib
from dataclasses import dataclass, field
from statistics import median
from typing import Optional

# 一次完整往返的成本：佣金双边 0.05% + 印花税 0.05% + 滑点 0.1%
COST_ROUND_TRIP = 0.002
HORIZONS = (1, 3, 5, 10, 20)
PRIMARY_HORIZON = 10
MIN_SAMPLE = 30
ITERATIONS = 200
MAX_P_VALUE = 0.10

# 连续字段规则扫描用的分位点
SCAN_QUANTILES = (0.2, 0.4, 0.6, 0.8)


@dataclass
class SymbolSeries:
    """单个标的的行情与某指标的逐根输出。"""

    symbol: str
    closes: list[float]
    times: list[int]
    values: list[dict]


@dataclass
class FieldEvaluation:
    field: str
    direction: str
    rule: str
    threshold: Optional[float]
    verdict: str
    sample_n: int
    raw_events: int
    hit_rate: Optional[float]
    avg_return: Optional[float]
    baseline_return: Optional[float]
    excess_return: Optional[float]
    p_value: Optional[float]
    decay: dict[int, Optional[float]] = field(default_factory=dict)
    stability: dict[str, Optional[float]] = field(default_factory=dict)


def _forward_returns(closes: list[float], horizon: int) -> list[Optional[float]]:
    """第 i 根收盘入场、持有 horizon 根的收益；样本不足为 None。"""
    result: list[Optional[float]] = [None] * len(closes)
    for index in range(len(closes) - horizon):
        entry = closes[index]
        if entry > 0:
            result[index] = closes[index + horizon] / entry - 1.0
    return result


def _net_return(forward: float, direction: str) -> float:
    """扣成本后的方向化收益：做空时价格下跌才是正收益。"""
    base = forward if direction == "long" else -forward
    return base - COST_ROUND_TRIP


def _entry_indexes(event_indexes: list[int], horizon: int, length: int) -> list[int]:
    """事件根的下一个根才是入场点；持有期内的事件不再重复计数。"""
    entries: list[int] = []
    last_entry = -10**9
    for event in event_indexes:
        entry = event + 1
        if entry >= length or entry - last_entry < horizon:
            continue
        entries.append(entry)
        last_entry = entry
    return entries


def _mean(values: list[float]) -> Optional[float]:
    return sum(values) / len(values) if values else None


def _pooled_mean(summaries: list[tuple[float, int]]) -> Optional[float]:
    """summaries 是 (该标的的收益总和, 样本数)：池化均值 = 总和之和 / 样本数之和。

    注意不能写成 total * weight——那会把已经求过和的数值再乘一次样本数。
    """
    total_weight = sum(weight for _, weight in summaries)
    if total_weight <= 0:
        return None
    return sum(total for total, _ in summaries) / total_weight


def _event_returns(
    series: list[SymbolSeries],
    selected: list[list[int]],
    direction: str,
    horizon: int,
) -> tuple[list[float], list[int], list[list[int]]]:
    """汇总所有标的的入场点净收益、对应时间，以及每个标的的入场点列表。"""
    returns: list[float] = []
    times: list[int] = []
    entries_by_symbol: list[list[int]] = []
    for index, item in enumerate(series):
        forwards = _forward_returns(item.closes, horizon)
        entries = _entry_indexes(selected[index], horizon, len(item.closes))
        entries_by_symbol.append(entries)
        for entry in entries:
            forward = forwards[entry]
            if forward is None:
                continue
            returns.append(_net_return(forward, direction))
            times.append(item.times[entry])
    return returns, times, entries_by_symbol


def _baseline(series: list[SymbolSeries], horizon: int) -> Optional[float]:
    """基线：所有标的、所有可入场点的平均前瞻收益，同样扣一次往返成本。

    事件收益已扣成本，基线不扣会让超额系统性偏低一个成本。
    """
    summaries: list[tuple[float, int]] = []
    for item in series:
        values = [value for value in _forward_returns(item.closes, horizon) if value is not None]
        if values:
            summaries.append((sum(values), len(values)))
    mean = _pooled_mean(summaries)
    return None if mean is None else mean - COST_ROUND_TRIP


def _p_value(
    series: list[SymbolSeries],
    entries_by_symbol: list[list[int]],
    direction: str,
    horizon: int,
    observed: float,
    seed: int,
) -> Optional[float]:
    """随机化检验：随机抽同样多的入场点，看随机均值 ≥ 观测值的比例。"""
    forwards = [_forward_returns(item.closes, horizon) for item in series]
    candidates = [
        [index for index, value in enumerate(pattern) if value is not None]
        for pattern in forwards
    ]
    rng = random.Random(seed)
    random_means: list[float] = []
    for _ in range(ITERATIONS):
        summaries: list[tuple[float, int]] = []
        for index, count in enumerate(len(item) for item in entries_by_symbol):
            if count <= 0 or not candidates[index]:
                continue
            picks = [rng.choice(candidates[index]) for _ in range(count)]
            values = [_net_return(forwards[index][pick], direction) for pick in picks]  # type: ignore[arg-type]
            summaries.append((sum(values), len(values)))
        mean = _pooled_mean(summaries)
        if mean is not None:
            random_means.append(mean)
    if not random_means:
        return None
    hits = sum(1 for mean in random_means if mean >= observed)
    return (hits + 1) / (len(random_means) + 1)


def _reward_risk(values: list[float]) -> Optional[float]:
    """平均盈利 / 平均亏损绝对值；没有亏损时返回 None。"""
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    if not wins or not losses:
        return None
    return sum(wins) / len(wins) / abs(sum(losses) / len(losses))


def _decay(series: list[SymbolSeries], selected: list[list[int]], direction: str) -> dict[int, Optional[float]]:
    result: dict[int, Optional[float]] = {}
    for horizon in HORIZONS:
        returns, _, _ = _event_returns(series, selected, direction, horizon)
        mean = _mean(returns)
        result[horizon] = None if mean is None else round(mean, 6)
    return result


def _stability(
    series: list[SymbolSeries], selected: list[list[int]], direction: str,
) -> dict[str, Optional[float]]:
    """按事件时间中位数切成前后两段，各算净收益均值。"""
    returns, times, _ = _event_returns(series, selected, direction, PRIMARY_HORIZON)
    if not returns:
        return {"first_half": None, "second_half": None}
    midpoint = median(times)
    first = [value for value, time in zip(returns, times) if time <= midpoint]
    second = [value for value, time in zip(returns, times) if time > midpoint]
    return {
        "first_half": None if not first else round(_mean(first) or 0.0, 6),
        "second_half": None if not second else round(_mean(second) or 0.0, 6),
    }


def _decide(
    sample_n: int,
    avg_return: Optional[float],
    excess: Optional[float],
    p_value: Optional[float],
    stability: dict[str, Optional[float]],
) -> str:
    if sample_n < MIN_SAMPLE or avg_return is None or excess is None or p_value is None:
        return "insufficient"
    if p_value > MAX_P_VALUE:
        return "weak"
    halves = [stability.get("first_half"), stability.get("second_half")]
    both_positive = all(value is not None and value > 0 for value in halves)
    if avg_return > 0 and excess > 0 and both_positive:
        return "valid"
    if avg_return < 0:
        return "rejected"
    return "weak"


def _hit_rate(returns: list[float]) -> Optional[float]:
    if not returns:
        return None
    return round(sum(1 for value in returns if value > 0) / len(returns), 4)


def _build_evaluation(
    field_name: str,
    direction: str,
    rule: str,
    threshold: Optional[float],
    series: list[SymbolSeries],
    selected: list[list[int]],
    p_adjust: int = 1,
) -> FieldEvaluation:
    returns, _, entries = _event_returns(series, selected, direction, PRIMARY_HORIZON)
    sample_n = len(returns)
    avg_return = _mean(returns)
    baseline = _baseline(series, PRIMARY_HORIZON)
    excess = None if avg_return is None or baseline is None else avg_return - baseline
    seed = zlib.crc32(f"{field_name}|{direction}|{rule}|{threshold}".encode("utf-8"))
    p_value = (
        None if avg_return is None
        else _p_value(series, entries, direction, PRIMARY_HORIZON, avg_return, seed)
    )
    if p_value is not None and p_adjust > 1:
        p_value = min(1.0, p_value * p_adjust)
    stability = _stability(series, selected, direction)
    return FieldEvaluation(
        field=field_name,
        direction=direction,
        rule=rule,
        threshold=threshold,
        verdict=_decide(sample_n, avg_return, excess, p_value, stability),
        sample_n=sample_n,
        raw_events=sum(len(item) for item in selected),
        hit_rate=_hit_rate(returns),
        avg_return=None if avg_return is None else round(avg_return, 6),
        baseline_return=None if baseline is None else round(baseline, 6),
        excess_return=None if excess is None else round(excess, 6),
        p_value=None if p_value is None else round(p_value, 4),
        decay=_decay(series, selected, direction),
        stability=stability,
    )


def _rank(item: FieldEvaluation) -> tuple[int, float]:
    significant = 1 if item.p_value is not None and item.p_value <= MAX_P_VALUE else 0
    return significant, abs(item.excess_return or 0.0)


def evaluate_event_field(
    series: list[SymbolSeries],
    field_name: str,
    direction: str,
) -> FieldEvaluation:
    """形态/事件字段：字段非零即事件。direction 为 none 时两个方向都试，取证据更强的一侧。"""
    selected = [
        [index for index, row in enumerate(item.values) if row.get(field_name) not in (None, 0)]
        for item in series
    ]
    sides = [direction] if direction in ("long", "short") else ["long", "short"]
    candidates = [
        _build_evaluation(field_name, side, "nonzero", None, series, selected)
        for side in sides
    ]
    return candidates[0] if len(candidates) == 1 else max(candidates, key=_rank)


def evaluate_continuous_field(series: list[SymbolSeries], field_name: str) -> FieldEvaluation:
    """连续字段：在分位点上扫 > / < 两组规则，按多重检验校正后的证据选一条。"""
    pooled = sorted(
        float(row[field_name])
        for item in series
        for row in item.values
        if isinstance(row.get(field_name), (int, float))
    )
    if len(pooled) < MIN_SAMPLE:
        return _build_evaluation(field_name, "long", "gt", None, series, [[] for _ in series])

    thresholds = sorted({
        pooled[min(len(pooled) - 1, int(len(pooled) * quantile))]
        for quantile in SCAN_QUANTILES
    })
    rules = [(mode, threshold) for threshold in thresholds for mode in ("gt", "lt")]
    candidates: list[FieldEvaluation] = []
    for mode, threshold in rules:
        selected = [
            [
                index for index, row in enumerate(item.values)
                if isinstance(row.get(field_name), (int, float))
                and (float(row[field_name]) > threshold if mode == "gt" else float(row[field_name]) < threshold)
            ]
            for item in series
        ]
        for side in ("long", "short"):
            candidates.append(_build_evaluation(
                field_name, side, mode, threshold, series, selected, p_adjust=len(rules) * 2,
            ))
    return max(candidates, key=_rank)
