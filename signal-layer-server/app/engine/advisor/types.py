"""策略建议引擎：候选策略的数据结构。

这里的对象都是纯数据，不依赖数据库与外部服务，便于单测与复用。
"""

from __future__ import annotations

from dataclasses import dataclass, field

# 风险调整收益的上限：防止"零回撤"把排序带偏
MAX_RISK_ADJUSTED = 10.0


# ── 物化后的单个级别数据 ────────────────────────────────────────────────

@dataclass
class LevelSeries:
    """某个级别上物化好的K线与指标序列。

    indicators 的键是 indicator_key()，值是"字段 -> 逐根值"。
    field 取不到值时用 None 表示（样本不足）。
    """

    level: str
    times: list[int]
    opens: list[float]
    highs: list[float]
    lows: list[float]
    closes: list[float]
    volumes: list[float]
    atr: list[float | None] = field(default_factory=list)
    indicators: dict[str, dict[str, list[float | None]]] = field(default_factory=dict)
    # 缠论买卖点：类型 -> 该点所在K线时间的有序列表
    chan_points: dict[str, list[int]] = field(default_factory=dict)

    def series(self, key: str, name: str) -> list[float | None] | None:
        return self.indicators.get(key, {}).get(name)

    def index_of_time(self, time: int) -> int | None:
        """二分查找某时间对应的下标（LevelSeries.times 升序）。"""
        from bisect import bisect_left

        index = bisect_left(self.times, time)
        if index < len(self.times) and self.times[index] == time:
            return index
        return None


def indicator_key(indicator_type: str, params: dict) -> str:
    """指标参数组合的稳定键（与后端缓存键同样的思路：参数排序后拼接）。"""
    parts = "_".join(f"{name}={params[name]}" for name in sorted(params))
    return f"{indicator_type}:{parts}" if parts else indicator_type


# ── 候选策略 ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Rule:
    """一个判定规则。

    kind:
      - cross:      left 上穿/下穿 right（right 为常量或另一个序列）
      - compare:    left 大于/小于 right
      - direction:  left 上行/下行（与上一根比较）
      - chan_point: 该级别出现指定缠论买卖点
    """

    kind: str
    direction: str                      # above / below / rising / falling
    label: str                          # 人类可读，如 "MA10 上穿"
    left_field: str | None = None       # 指标字段；kind 为 chan_point 时为空
    left_key: str | None = None         # 指标参数键；为空表示价格序列
    right_field: str | None = None      # 与另一个指标序列比较时使用
    right_key: str | None = None
    right_value: float | None = None    # 与常量比较时使用
    chan_point: str | None = None       # buy1 / buy2 / buy3

    def describe(self) -> str:
        return self.label


@dataclass(frozen=True)
class ExitSpec:
    """出场参数。与入场一起搜索，避免止盈过小把胜率刷高。"""

    stop_loss_type: str          # atr / fixed_pct / none
    stop_loss_value: float
    take_profit_type: str        # rr_ratio / fixed_pct / none
    take_profit_value: float

    def describe(self) -> str:
        parts: list[str] = []
        if self.stop_loss_type == "atr":
            parts.append(f"止损 ATR×{self.stop_loss_value}")
        elif self.stop_loss_type == "fixed_pct":
            parts.append(f"止损 {self.stop_loss_value}%")
        if self.take_profit_type == "rr_ratio":
            parts.append(f"止盈 盈亏比 1:{self.take_profit_value}")
        elif self.take_profit_type == "fixed_pct":
            parts.append(f"止盈 {self.take_profit_value}%")
        return "、".join(parts) if parts else "无固定止损止盈"


@dataclass(frozen=True)
class Candidate:
    """一个待评估的策略候选。

    primary_level 决定模拟与统计所在的K线（也对应实盘推送的节流粒度）；
    entry_level 是入场规则实际求值的级别——指标类候选与主周期一致，
    缠论类候选取更细的次级级别（"次级别一买"），求值后再对齐到主周期K线。
    """

    id: str
    family: str
    primary_level: str
    entry_level: str
    entry: Rule
    exit: ExitSpec
    # 仅用于说明：入场取自哪个次级级别
    secondary_level: str | None = None

    def describe(self) -> str:
        parts = [f"{self.primary_level} {self.entry.describe()}"]
        parts.append(self.exit.describe())
        return "；".join(parts)


# ── 评估结果 ────────────────────────────────────────────────────────────

@dataclass
class TradeStats:
    """一段数据上的交易统计。"""

    trades: int = 0
    wins: int = 0
    total_return: float = 0.0
    max_drawdown: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    bars: int = 0

    @property
    def win_rate(self) -> float:
        return (self.wins / self.trades * 100.0) if self.trades else 0.0

    @property
    def expectancy(self) -> float:
        """每笔平均收益（%）。"""
        return (self.total_return / self.trades) if self.trades else 0.0

    @property
    def profit_factor(self) -> float:
        if self.gross_loss <= 0:
            return 999.0 if self.gross_profit > 0 else 0.0
        return self.gross_profit / self.gross_loss

    @property
    def frequency(self) -> float:
        """每根K线的期望交易次数，跨标的/周期可比。"""
        return (self.trades / self.bars) if self.bars else 0.0

    @property
    def risk_adjusted(self) -> float:
        """风险调整收益：总收益 / 最大回撤。

        回撤为 0 时按上限计，并且正负两侧都夹紧——否则"零回撤但收益极小"的
        候选会拿到 999 这种极值，把排序完全带偏。
        """
        if self.max_drawdown <= 0:
            return MAX_RISK_ADJUSTED if self.total_return > 0 else 0.0
        ratio = self.total_return / self.max_drawdown
        return max(min(ratio, MAX_RISK_ADJUSTED), -MAX_RISK_ADJUSTED)


@dataclass
class WindowResult:
    """滚动评估中的一个窗口结果。"""

    index: int
    in_sample: TradeStats
    out_of_sample: TradeStats


@dataclass
class CandidateResult:
    """一个候选的完整评估结果。"""

    candidate: Candidate
    windows: list[WindowResult] = field(default_factory=list)
    out_of_sample: TradeStats = field(default_factory=TradeStats)
    in_sample: TradeStats = field(default_factory=TradeStats)
    score: float = 0.0
    passed_constraints: bool = False
    rejected_reason: str | None = None
    plateau_stable: bool = False
    notes: list[str] = field(default_factory=list)
