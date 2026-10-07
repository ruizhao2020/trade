"""候选策略的搜索：滚动分段评估 + 样本外留出 + 稳健性判定。

时间轴切法（按时间顺序切，绝不随机切）：

    |---------- 选定期（用于排序） ----------|--- 留出期（只用于报告） ---|
    |  段1  |  段2  |  段3  |                 （选定期内再分若干段做滚动目标）

- 约束过滤与排序只用选定期，避免"用未来数据挑参数"；
- 留出期完全不参与选择，用来给出真正样本外的数字；
- 稳健性用参数邻域（M10 的邻居 M9/M11）判定，防止选出参数尖峰。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.engine.advisor.registry import INDICATOR_SPACES
from app.engine.advisor.scoring import Constraints, ScoreBreakdown, check_constraints, score_windows
from app.engine.advisor.signals import align_signal_to, rule_signal
from app.engine.advisor.simulate import DEFAULT_TIMEOUT_BARS, simulate_trades, stats_from_trades
from app.engine.advisor.types import Candidate, CandidateResult, LevelSeries, WindowResult, indicator_key

NEIGHBOR_SCORE_RATIO = 0.5


@dataclass(frozen=True)
class SearchConfig:
    constraints: Constraints = Constraints()
    selection_ratio: float = 0.7
    segments: int = 3
    budget: int = 4000
    timeout_bars: int = DEFAULT_TIMEOUT_BARS
    min_bars: int = 120


@dataclass
class SearchOutcome:
    results: list[CandidateResult] = field(default_factory=list)
    rejected: list[CandidateResult] = field(default_factory=list)
    evaluated: int = 0
    truncated: bool = False
    selection_bounds: tuple[int, int] = (0, 0)
    holdout_bounds: tuple[int, int] = (0, 0)
    segment_bounds: list[tuple[int, int]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _bounds(size: int, config: SearchConfig) -> tuple[tuple[int, int], tuple[int, int], list[tuple[int, int]]]:
    selection_end = int(size * config.selection_ratio)
    if selection_end <= 0 or selection_end >= size:
        return (0, size), (size, size), []
    step = max(1, selection_end // max(1, config.segments))
    segments: list[tuple[int, int]] = []
    for index in range(0, selection_end, step):
        segments.append((index, min(index + step, selection_end)))
    return (0, selection_end), (selection_end, size), segments


def _entry_signal(candidate: Candidate, levels: dict[str, LevelSeries]) -> list[bool] | None:
    """入场信号：在 entry_level 上求值；若它不是主周期，则对齐到主周期K线。"""
    primary = levels.get(candidate.primary_level)
    entry_series = levels.get(candidate.entry_level)
    if primary is None or entry_series is None:
        return None
    signal = rule_signal(entry_series, candidate.entry)
    if candidate.entry_level != candidate.primary_level:
        return align_signal_to(primary, entry_series, signal)
    return signal


def evaluate_candidate(
    candidate: Candidate,
    levels: dict[str, LevelSeries],
    config: SearchConfig,
    bounds: tuple[tuple[int, int], tuple[int, int], list[tuple[int, int]]],
) -> CandidateResult | None:
    """评估单个候选：一次遍历产出逐笔交易，再派生整体/分段/留出统计。"""
    primary = levels.get(candidate.primary_level)
    if primary is None or len(primary.times) < config.min_bars:
        return None
    signal = _entry_signal(candidate, levels)
    if signal is None:
        return None

    (selection_start, selection_end), (holdout_start, holdout_end), segments = bounds
    trades = simulate_trades(
        primary, signal, candidate.exit,
        start=selection_start, end=holdout_end or selection_end,
        timeout_bars=config.timeout_bars,
    )
    selection_trades = [item for item in trades if item.entry_index < selection_end]
    holdout_trades = [item for item in trades if item.entry_index >= holdout_start]

    in_sample = stats_from_trades(selection_trades, max(0, selection_end - selection_start))
    out_of_sample = stats_from_trades(holdout_trades, max(0, holdout_end - holdout_start))

    windows: list[WindowResult] = []
    risks: list[float] = []
    for index, (start, end) in enumerate(segments):
        bucket = [item for item in selection_trades if start <= item.entry_index < end]
        segment_stats = stats_from_trades(bucket, max(0, end - start))
        risks.append(segment_stats.risk_adjusted)
        windows.append(WindowResult(index=index, in_sample=segment_stats, out_of_sample=segment_stats))

    result = CandidateResult(candidate=candidate, windows=windows, in_sample=in_sample, out_of_sample=out_of_sample)

    # 先算分再判约束：被约束淘汰的候选也要有分数，否则参数平台判定看不到它们，
    # 会把"邻居被约束过滤掉"误判成"邻居表现差"（实测平台通过率因此被压到 2.4%）。
    breakdown = _score(result, risks, config)
    result.score = breakdown.score
    result.notes.append(breakdown.describe())

    reason = check_constraints(in_sample, config.constraints)
    if reason:
        result.passed_constraints = False
        result.rejected_reason = reason
        return result

    result.passed_constraints = True
    return result


def _score(result: CandidateResult, risks: list[float], config: SearchConfig) -> ScoreBreakdown:
    return score_windows(risks, result.in_sample, config.constraints)


def _indicator_key_of(candidate: Candidate) -> str | None:
    """候选里带参数的那个指标键——可能出现在左值或右值。

    MA 这类规则是"价格 vs 指标"，指标在右值；MACD 这类是"指标 vs 指标"，
    两侧都是指标。只看左值会漏掉前者，让参数平台判定永远不生效。
    """
    return candidate.entry.left_key or candidate.entry.right_key


def _rule_signature(candidate: Candidate) -> tuple:
    """同族比较的分组键：**不含参数**，只保留"规则形态 + 指标类型 + 级别"。

    如果把带参数的 key 放进签名，每个参数值都会自成一组，永远找不到相邻参数，
    参数平台判定就会恒为 False。
    """
    entry = candidate.entry
    key = _indicator_key_of(candidate)
    return (
        entry.kind, entry.direction,
        entry.left_field if not entry.left_key else None,
        entry.right_field if not entry.right_key else None,
        entry.chan_point,
        key.split(":", 1)[0] if key else None,
        entry.right_value,
        candidate.primary_level, candidate.entry_level,
        # 出场参数必须进签名：否则同一规则的不同出场会共用同一个分数槽位，
        # 平台比较就会串到别的出场参数上。
        candidate.exit.describe(),
    )


def _neighbor_keys(candidate: Candidate) -> set[str]:
    """同一指标族内、参数只差一格（相邻）的规则键，用于参数平台判定。"""
    key = _indicator_key_of(candidate)
    if key is None or candidate.entry.kind == "chan_point":
        return set()
    indicator_type = key.split(":", 1)[0]
    space = next((item for item in INDICATOR_SPACES if item.indicator_type == indicator_type), None)
    if space is None:
        return set()

    current = _params_of(key)
    if not current:
        return set()
    keys: set[str] = set()
    for params in space.param_grid:
        diffs = [name for name in params if params[name] != current.get(name)]
        if len(diffs) != 1:
            continue
        name = diffs[0]
        grid_values = sorted({item[name] for item in space.param_grid if name in item})
        # 注意：要比的是"当前取值"是否在候选网格里，不是参数名——
        # 写成 `name not in grid_values` 会让条件恒为真，平台判定永远失效。
        if current.get(name) not in grid_values:
            continue
        index = grid_values.index(current[name])
        for offset in (-1, 1):
            neighbor = index + offset
            if 0 <= neighbor < len(grid_values) and params[name] == grid_values[neighbor]:
                keys.add(indicator_key(indicator_type, params))
    return keys


def _params_of(key: str) -> dict[str, float]:
    params: dict[str, float] = {}
    for part in key.split(":")[1:]:
        if "=" not in part:
            continue
        name, _, value = part.partition("=")
        try:
            params[name] = float(value)
        except ValueError:
            continue
    return params


def search(candidates: list[Candidate], levels: dict[str, LevelSeries], config: SearchConfig) -> SearchOutcome:
    """评估全部候选，按稳健分排序，并给出参数平台判定。"""
    outcome = SearchOutcome(truncated=False)
    if not candidates:
        outcome.notes.append("候选空间为空")
        return outcome

    # 各主周期的分段边界按该级别的K线数量计算
    bounds_by_level = {
        level: _bounds(len(series.times), config)
        for level, series in levels.items()
    }

    evaluated: list[CandidateResult] = []
    passed: list[CandidateResult] = []
    for candidate in candidates:
        bounds = bounds_by_level.get(candidate.primary_level)
        if bounds is None:
            continue
        result = evaluate_candidate(candidate, levels, config, bounds)
        if result is None:
            continue
        outcome.evaluated += 1
        evaluated.append(result)
        if result.passed_constraints:
            passed.append(result)

    passed.sort(key=lambda item: item.score, reverse=True)

    # 参数平台判定：相邻参数也应当站得住。
    # 用"全部已评估候选"的分数（含被约束淘汰者），否则邻居一旦被交易数等条件过滤掉，
    # 就会因为"找不到邻居"而被判成尖峰。
    scores_by_signature: dict[tuple, dict[str, float]] = {}
    for result in evaluated:
        signature = _rule_signature(result.candidate)
        scores_by_signature.setdefault(signature, {})[_indicator_key_of(result.candidate) or ""] = result.score

    for result in passed:
        neighbors = _neighbor_keys(result.candidate)
        if not neighbors:
            result.plateau_stable = False
            result.notes.append("无可比相邻参数，无法判定参数平台")
            continue
        key = _rule_signature(result.candidate)
        group = scores_by_signature.get(key, {})
        neighbor_scores = [group[item] for item in neighbors if item in group]
        if not neighbor_scores:
            result.plateau_stable = False
            result.notes.append("相邻参数未被评估，无法判定参数平台")
            continue
        best_neighbor = max(neighbor_scores)
        result.plateau_stable = best_neighbor >= result.score * NEIGHBOR_SCORE_RATIO
        if not result.plateau_stable:
            result.notes.append(
                f"参数平台不稳：相邻参数最好只有 {best_neighbor:.2f}，不足最优的 {NEIGHBOR_SCORE_RATIO:.0%}"
            )

    outcome.results = passed
    outcome.rejected = [item for item in evaluated if not item.passed_constraints]
    if levels:
        first = next(iter(levels.values()))
        outcome.selection_bounds, outcome.holdout_bounds, outcome.segment_bounds = bounds_by_level.get(
            first.level, ((0, 0), (0, 0), []),
        )
    return outcome
