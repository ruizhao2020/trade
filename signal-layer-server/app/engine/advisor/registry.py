"""候选策略的规则注册表。

设计目标：**新增指标只需要在这里登记元数据**（可搜索参数网格 + 规则声明），
搜索与评估的代码不需要任何改动。

序列引用（SeriesRef）写法：
  "price"      —— 该级别的收盘价
  "<字段名>"   —— 该指标自身输出的字段（如 macd 的 dif / dea）
  数字         —— 常量阈值（如 RSI 的 30 / 70）

规则声明 RuleSpec 的元组含义：
  (kind, direction, left, right, label_template)
label_template 里的 {param} 会被替换成当前参数值，便于生成人类可读文案。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Union

from app.engine.advisor.types import Candidate, ExitSpec, Rule, indicator_key

SeriesRef = Union[str, float]

# 按由粗到细排列，与前端 SUPPORTED_TIMEFRAME_IDS 保持一致
SUPPORTED_LEVELS: tuple[str, ...] = ("1d", "60m", "30m", "15m", "5m")


@dataclass(frozen=True)
class RuleSpec:
    kind: str
    direction: str
    left: SeriesRef
    right: SeriesRef | None
    label: str


@dataclass(frozen=True)
class IndicatorSpace:
    indicator_type: str
    family: str
    param_grid: tuple[dict, ...]
    rules: tuple[RuleSpec, ...]
    # 是否为"标签/状态"类指标（值不是连续序列，而是 0/1 之类的状态）
    discrete: bool = False


# ── 各指标的搜索空间 ────────────────────────────────────────────────────
#
# 字段名与引擎里 RenderSpec 的输出字段严格一致（改动指标输出时这里要同步）。

INDICATOR_SPACES: tuple[IndicatorSpace, ...] = (
    IndicatorSpace(
        indicator_type="ma", family="均线",
        # 密度要够：参数平台判定靠"相邻参数"（M10 的邻居是 M9/M11），
        # 网格太稀疏（5/10/20…）会让每个周期都变成孤立的尖峰。
        param_grid=tuple(
            {"period": period}
            for period in (5, 8, 9, 10, 11, 12, 20, 30, 60, 120, 260)
        ),
        rules=(
            RuleSpec("cross", "above", "price", "value", "价格上穿 MA{period}"),
            RuleSpec("cross", "below", "value", "price", "价格下穿 MA{period}"),
            RuleSpec("compare", "above", "price", "value", "收盘价在 MA{period} 上方持有"),
            RuleSpec("direction", "rising", "value", None, "MA{period} 上行时持有"),
        ),
    ),
    IndicatorSpace(
        indicator_type="macd", family="MACD",
        param_grid=({"fast": 12, "slow": 26, "signal": 9},),
        rules=(
            RuleSpec("cross", "above", "dif", "dea", "MACD 金叉（DIF 上穿 DEA）"),
            RuleSpec("cross", "below", "dif", "dea", "MACD 死叉（DIF 下穿 DEA）"),
            RuleSpec("compare", "above", "histogram", 0.0, "MACD 柱体转正"),
        ),
    ),
    IndicatorSpace(
        indicator_type="bollinger", family="布林带",
        param_grid=(
            {"period": 20, "std": 2.0},
            {"period": 20, "std": 2.5},
            {"period": 30, "std": 2.0},
        ),
        rules=(
            RuleSpec("cross", "above", "price", "lower", "价格上穿布林下轨（超跌反弹）"),
            RuleSpec("cross", "below", "price", "upper", "价格下穿布林上轨"),
            RuleSpec("compare", "above", "price", "middle", "收盘价在布林中轨上方持有"),
            RuleSpec("direction", "rising", "middle", None, "布林中轨上行时持有"),
        ),
    ),
    IndicatorSpace(
        indicator_type="kdj", family="KDJ",
        param_grid=({"n": 9, "m1": 3, "m2": 3},),
        rules=(
            RuleSpec("cross", "above", "k", "d", "KDJ 金叉（K 上穿 D）"),
            RuleSpec("cross", "below", "k", "d", "KDJ 死叉（K 下穿 D）"),
            RuleSpec("compare", "below", "j", 0.0, "J 值低于 0（超卖）"),
        ),
    ),
    IndicatorSpace(
        indicator_type="rsi", family="RSI",
        param_grid=({"period": 14}, {"period": 6}),
        rules=(
            RuleSpec("compare", "below", "value", 30.0, "RSI{period} 低于 30（超卖）"),
            RuleSpec("cross", "above", "value", 50.0, "RSI{period} 上穿 50"),
        ),
    ),
    IndicatorSpace(
        indicator_type="volume", family="成交量",
        param_grid=({"relative_period": 20},),
        rules=(
            RuleSpec("compare", "above", "relative_volume", 1.5, "相对量能 > 1.5（放量）"),
            RuleSpec("compare", "below", "relative_volume", 0.7, "相对量能 < 0.7（缩量）"),
            RuleSpec("compare", "above", "increase_streak", 2.0, "连续放量 ≥ 3 根"),
        ),
    ),
    IndicatorSpace(
        indicator_type="volume_structure", family="量柱结构",
        param_grid=({"lookback": 20, "key_ratio_min": 1.8, "confirm_bars": 3, "break_tolerance": 0.0},),
        rules=(
            RuleSpec("compare", "above", "golden_confirmed", 0.5, "出现黄金柱（确认）"),
            RuleSpec("compare", "above", "key_pillar", 0.5, "出现关键量柱"),
        ),
        discrete=True,
    ),
    IndicatorSpace(
        indicator_type="chip_distribution", family="筹码分布",
        param_grid=({"lookback": 60},),
        rules=(
            RuleSpec("compare", "above", "above_average_cost", 0.5, "价格站上平均成本"),
            RuleSpec("cross", "above", "price", "average_cost", "价格上穿平均成本"),
            RuleSpec("compare", "below", "concentration70", 0.15, "筹码高度集中（集中度 < 15%）"),
            RuleSpec("compare", "above", "price_vs_average_pct", 8.0, "价格高于平均成本 8% 以上"),
        ),
        discrete=True,
    ),
)

# 缠论：不是参数化指标，而是结构信号
CHAN_FAMILY = "缠论"
CHAN_POINTS: tuple[tuple[str, str], ...] = (
    ("buy1", "次级别一买"),
    ("buy2", "次级别二买"),
    ("buy3", "次级别三买"),
)

# 出场参数网格：与入场一起搜索，避免"止盈设小刷高胜率"的偏差
EXIT_GRID: tuple[ExitSpec, ...] = (
    ExitSpec("atr", 2.0, "rr_ratio", 2.0),
    ExitSpec("atr", 2.0, "rr_ratio", 3.0),
    ExitSpec("atr", 3.0, "rr_ratio", 2.0),
    ExitSpec("fixed_pct", 5.0, "rr_ratio", 2.0),
    ExitSpec("fixed_pct", 8.0, "rr_ratio", 3.0),
    ExitSpec("fixed_pct", 5.0, "fixed_pct", 10.0),
)


def _stable_id(*parts: str) -> str:
    """跨进程稳定的短哈希：Python 的 hash() 受 PYTHONHASHSEED 影响，不能用来做可复现 ID。"""
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:8]


def _resolve_label(template: str, params: dict) -> str:
    try:
        return template.format(**params)
    except (KeyError, IndexError):
        return template


def _build_rule(spec: RuleSpec, key: str, params: dict) -> Rule:
    def ref(value: SeriesRef | None) -> tuple[str | None, str | None, float | None]:
        if value is None:
            return None, None, None
        if isinstance(value, (int, float)):
            return None, None, float(value)
        if value == "price":
            return "close", None, None
        return value, key, None

    left_field, left_key, left_value = ref(spec.left)
    if left_value is not None:
        # 常量放在左侧没有实际意义，注册表里不会这样写
        raise ValueError("规则左值不能是常量")
    right_field, right_key, right_value = ref(spec.right)
    return Rule(
        kind=spec.kind,
        direction=spec.direction,
        label=_resolve_label(spec.label, params),
        left_field=left_field,
        left_key=left_key,
        right_field=right_field,
        right_key=right_key,
        right_value=right_value,
    )


def secondary_levels_for(primary_level: str) -> tuple[str, ...]:
    """主周期的可选次级周期：只允许比它更细的级别。"""
    if primary_level not in SUPPORTED_LEVELS:
        return ()
    index = SUPPORTED_LEVELS.index(primary_level)
    return SUPPORTED_LEVELS[index + 1:]


def _spread_across_families(candidates: list[Candidate], budget: int) -> list[Candidate]:
    """按指标族轮转取样。

    直接按顺序前缀截断会让"注册在前的指标"吃掉整个预算（例如 MA 有上千个
    组合，结果其余指标一个都没被评估）。轮转取样保证每个族都有代表，
    且结果仍然是确定性的。
    """
    buckets: dict[str, list[Candidate]] = {}
    order: list[str] = []
    for candidate in candidates:
        if candidate.family not in buckets:
            buckets[candidate.family] = []
            order.append(candidate.family)
        buckets[candidate.family].append(candidate)

    selected: list[Candidate] = []
    index = 0
    while len(selected) < budget:
        added = False
        for family in order:
            bucket = buckets[family]
            if index < len(bucket):
                selected.append(bucket[index])
                added = True
                if len(selected) >= budget:
                    break
        if not added:
            break
        index += 1
    return selected


def build_candidate_space(
    *,
    levels: tuple[str, ...] = SUPPORTED_LEVELS,
    exit_grid: tuple[ExitSpec, ...] = EXIT_GRID,
    budget: int = 4000,
) -> tuple[list[Candidate], bool]:
    """生成候选策略空间。

    返回 (候选列表, 是否因预算被截断)。
    顺序是确定性的，同样的输入永远得到同样的候选集合——便于结论可复现。
    """
    candidates: list[Candidate] = []

    for space in INDICATOR_SPACES:
        for params in space.param_grid:
            key = indicator_key(space.indicator_type, params)
            for spec in space.rules:
                rule = _build_rule(spec, key, params)
                param_tag = "_".join(f"{name}{params[name]}" for name in sorted(params))
                for primary in levels:
                    for exit_spec in exit_grid:
                        candidates.append(Candidate(
                            id=f"{space.indicator_type}:{param_tag}:{spec.kind}{spec.direction}:{rule.left_field}:{primary}:{_stable_id(exit_spec.describe())}",
                            family=space.family,
                            primary_level=primary,
                            entry_level=primary,
                            entry=rule,
                            exit=exit_spec,
                        ))

    # 缠论：主周期给节奏约束，入场用次级周期的买卖点（"次级别一买"）
    for point, label in CHAN_POINTS:
        for primary in levels:
            for secondary in secondary_levels_for(primary):
                for exit_spec in exit_grid:
                    candidates.append(Candidate(
                        id=f"chan:{point}:{primary}:{secondary}:{_stable_id(exit_spec.describe())}",
                        family=CHAN_FAMILY,
                        primary_level=primary,
                        entry_level=secondary,
                        secondary_level=secondary,
                        entry=Rule(kind="chan_point", direction="above", label=f"{label}（{secondary}）", chan_point=point),
                        exit=exit_spec,
                    ))

    truncated = len(candidates) > budget
    return _spread_across_families(candidates, budget), truncated
