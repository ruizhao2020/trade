"""候选策略的约束过滤与稳健评分。

评分原则（对应"滚动目标 + 胜率/频率约束"）：
  - 主项是**各滚动窗口样本外**风险调整收益的**中位数**——用中位数抗单段暴利；
  - 稳定性因子惩罚"只有个别窗口赚钱"的候选；
  - 胜率与频率作为温和修正，避免选出"高胜率但期望差"或"高频噪声"的候选；
  - 硬约束（交易数、胜率下限、频率区间、样本外为正）不满足直接淘汰，不能用分数补。
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from app.engine.advisor.types import TradeStats


@dataclass(frozen=True)
class Constraints:
    """硬约束。全部可在运行时覆盖。"""

    min_trades: int = 20
    min_win_rate: float = 40.0
    min_frequency: float = 0.0
    max_frequency: float = 0.5
    min_out_of_sample_return: float = 0.0

    def describe(self) -> str:
        return (
            f"交易数 ≥ {self.min_trades}、胜率 ≥ {self.min_win_rate:.0f}%、"
            f"频率 {self.min_frequency:.3f}~{self.max_frequency:.3f} 次/根、"
            f"样本外收益 > {self.min_out_of_sample_return:.1f}%"
        )


@dataclass
class ScoreBreakdown:
    """评分分项，用于向用户解释"为什么是它"。"""

    median_oos: float = 0.0
    stability: float = 0.0
    win_factor: float = 0.0
    frequency_factor: float = 0.0
    score: float = 0.0
    components: dict = field(default_factory=dict)

    def describe(self) -> str:
        return (
            f"窗口样本外风险调整收益中位数 {self.median_oos:.2f} × "
            f"稳定性 {self.stability:.2f} × 胜率因子 {self.win_factor:.2f} × "
            f"频率因子 {self.frequency_factor:.2f} = {self.score:.2f}"
        )


def check_constraints(stats: TradeStats, constraints: Constraints) -> str | None:
    """返回 None 表示通过，否则返回淘汰原因。"""
    if stats.trades < constraints.min_trades:
        return f"交易数不足（{stats.trades} < {constraints.min_trades}）"
    if stats.win_rate < constraints.min_win_rate:
        return f"胜率不足（{stats.win_rate:.1f}% < {constraints.min_win_rate:.0f}%）"
    if stats.frequency < constraints.min_frequency:
        return f"频率过低（{stats.frequency:.3f} < {constraints.min_frequency:.3f}）"
    if stats.frequency > constraints.max_frequency:
        return f"频率过高（{stats.frequency:.3f} > {constraints.max_frequency:.3f}）"
    if stats.total_return <= constraints.min_out_of_sample_return:
        return f"样本外无正收益（{stats.total_return:.2f}%）"
    return None


def _win_factor(win_rate: float) -> float:
    """胜率 50% 以上不加分，低于 50% 温和衰减（不主导排序）。"""
    if win_rate >= 50:
        return 1.0
    return max(0.5, 0.5 + win_rate / 100.0)


def _frequency_factor(frequency: float, constraints: Constraints) -> float:
    """落在目标频率区间内为 1，越界温和衰减。"""
    if frequency <= 0:
        return 0.5
    if constraints.min_frequency <= frequency <= constraints.max_frequency:
        return 1.0
    if frequency < constraints.min_frequency:
        ratio = frequency / constraints.min_frequency if constraints.min_frequency else 1.0
    else:
        ratio = constraints.max_frequency / frequency if frequency else 0.0
    return max(0.5, 0.5 + ratio / 2)


def score_windows(
    window_risks: list[float],
    stats: TradeStats,
    constraints: Constraints,
) -> ScoreBreakdown:
    """按各窗口的样本外风险调整收益给出总分与分项。"""
    positive_windows = [item for item in window_risks if item > 0]
    median_oos = statistics.median(window_risks) if window_risks else 0.0
    # 稳定性：正收益窗口占比（无窗口时按 0 处理，避免"没数据=满分"）
    stability = (len(positive_windows) / len(window_risks)) if window_risks else 0.0
    win_factor = _win_factor(stats.win_rate)
    frequency_factor = _frequency_factor(stats.frequency, constraints)

    base = max(median_oos, 0.0)
    score = base * stability * win_factor * frequency_factor
    return ScoreBreakdown(
        median_oos=round(median_oos, 4),
        stability=round(stability, 4),
        win_factor=round(win_factor, 4),
        frequency_factor=round(frequency_factor, 4),
        score=round(score, 4),
        components={
            "windows": len(window_risks),
            "positive_windows": len(positive_windows),
            "win_rate": round(stats.win_rate, 2),
            "frequency": round(stats.frequency, 4),
            "trades": stats.trades,
            "total_return": round(stats.total_return, 2),
            "max_drawdown": round(stats.max_drawdown, 2),
            "profit_factor": round(stats.profit_factor, 2),
        },
    )
