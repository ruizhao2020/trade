"""策略建议引擎的纯逻辑测试（不依赖数据库与外部服务）。"""

import math

from app.engine.advisor.profile import basic_profile
from app.engine.advisor.registry import (
    EXIT_GRID,
    INDICATOR_SPACES,
    build_candidate_space,
    indicator_key,
    secondary_levels_for,
)
from app.engine.advisor.scoring import Constraints, check_constraints, score_windows
from app.engine.advisor.search import SearchConfig, search
from app.engine.advisor.signals import align_signal_to, combine, rule_signal
from app.engine.advisor.simulate import simulate, simulate_trades, stats_from_trades
from app.engine.advisor.types import Candidate, ExitSpec, LevelSeries, Rule, TradeStats


def make_level(level: str, closes: list[float], *, highs=None, lows=None, times=None) -> LevelSeries:
    size = len(closes)
    return LevelSeries(
        level=level,
        times=times or [1_700_000_000_000 + index * 86_400_000 for index in range(size)],
        opens=list(closes),
        highs=list(highs if highs is not None else [value * 1.01 for value in closes]),
        lows=list(lows if lows is not None else [value * 0.99 for value in closes]),
        closes=list(closes),
        volumes=[100.0] * size,
    )


def trend_closes(size: int = 300, step: float = 0.005) -> list[float]:
    return [100.0 * (1 + step) ** index for index in range(size)]


# ── 注册表 ──────────────────────────────────────────────────────────────

def test_candidate_space_is_deterministic_and_respects_budget():
    first, truncated_first = build_candidate_space(budget=100000)
    second, _ = build_candidate_space(budget=100000)

    assert [item.id for item in first] == [item.id for item in second]
    assert truncated_first is False

    limited, truncated = build_candidate_space(budget=50)
    assert len(limited) == 50
    assert truncated is True


def test_secondary_levels_are_strictly_finer():
    assert secondary_levels_for("1d") == ("60m", "30m", "15m", "5m")
    assert secondary_levels_for("30m") == ("15m", "5m")
    assert secondary_levels_for("5m") == ()


def test_every_registered_indicator_is_searchable():
    types = {space.indicator_type for space in INDICATOR_SPACES}
    # 用户要求的七个指标 + RSI 都要在候选空间里
    assert {"ma", "macd", "bollinger", "kdj", "rsi", "volume", "volume_structure", "chip_distribution"} <= types
    for space in INDICATOR_SPACES:
        assert space.param_grid, f"{space.indicator_type} 没有可搜索参数"
        assert space.rules, f"{space.indicator_type} 没有可用规则"


def test_chan_candidates_always_use_a_finer_secondary():
    candidates, _ = build_candidate_space()
    chan = [item for item in candidates if item.entry.kind == "chan_point"]
    assert chan, "缠论候选不应为空"
    for item in chan:
        assert item.secondary_level in secondary_levels_for(item.primary_level)
        # 入场在次级级别求值，再对齐到主周期
        assert item.entry_level == item.secondary_level
        assert item.entry_level != item.primary_level


# ── 信号 ────────────────────────────────────────────────────────────────

def test_compare_and_direction_rules():
    level = make_level("1d", [10.0, 11.0, 12.0, 11.0])
    level.indicators[indicator_key("ma", {"period": 2})] = {"value": [None, 10.5, 11.5, 11.5]}

    above = rule_signal(level, Rule(kind="compare", direction="above", label="", left_field="close", left_key=None, right_field="value", right_key=indicator_key("ma", {"period": 2})))
    assert above == [False, True, True, False]

    rising = rule_signal(level, Rule(kind="direction", direction="rising", label="", left_field="close", left_key=None))
    assert rising == [False, True, True, False]


def test_cross_rule_requires_an_actual_cross():
    level = make_level("1d", [10.0, 10.0, 12.0])
    signal = rule_signal(level, Rule(
        kind="cross", direction="above", label="",
        left_field="close", left_key=None, right_value=11.0,
    ))
    assert signal == [False, False, True]


def test_missing_values_never_produce_signals():
    level = make_level("1d", [10.0, 11.0])
    level.indicators[indicator_key("ma", {"period": 5})] = {"value": [None, None]}
    signal = rule_signal(level, Rule(
        kind="compare", direction="above", label="",
        left_field="close", left_key=None, right_field="value", right_key=indicator_key("ma", {"period": 5}),
    ))
    assert signal == [False, False]


def test_chan_point_rule_marks_the_point_bar():
    level = make_level("1d", [1.0, 2.0, 3.0])
    level.chan_points["buy1"] = [level.times[1]]
    signal = rule_signal(level, Rule(kind="chan_point", direction="above", label="", chan_point="buy1"))
    assert signal == [False, True, False]


def test_align_signal_maps_secondary_onto_primary_bars():
    primary = make_level("1d", [1.0, 2.0, 3.0], times=[100, 200, 300])
    secondary = make_level("30m", [1.0, 1.0, 1.0], times=[50, 150, 250])
    aligned = align_signal_to(primary, secondary, [True, False, True])
    # 主周期 100 -> 次级最后一根 <=100 是 50(True)；200 -> 150(False)；300 -> 250(True)
    assert aligned == [True, False, True]


def test_combine_is_logical_and():
    assert combine([True, True], [True, False]) == [True, False]


# ── 模拟 ────────────────────────────────────────────────────────────────

def test_simulate_hits_take_profit_and_reports_metrics():
    level = make_level("1d", [100.0, 101.0, 120.0, 121.0], highs=[101.0, 102.0, 121.0, 122.0], lows=[99.0, 100.0, 110.0, 120.0])
    signal = [True, False, False, False]
    spec = ExitSpec("fixed_pct", 5.0, "fixed_pct", 10.0)

    stats = simulate(level, signal, spec)

    assert stats.trades == 1
    assert stats.wins == 1
    assert abs(stats.total_return - 10.0) < 1e-6
    assert stats.win_rate == 100.0
    assert stats.frequency == 1 / 4


def test_simulate_stop_loss_wins_over_take_profit_in_same_bar():
    """同一根K线同时触及止损与止盈时按先止损处理（保守）。"""
    level = make_level(
        "1d", [100.0, 100.0],
        highs=[100.0, 130.0], lows=[100.0, 80.0],
    )
    spec = ExitSpec("fixed_pct", 10.0, "fixed_pct", 20.0)

    stats = simulate(level, [True, False], spec)

    assert stats.trades == 1
    assert stats.wins == 0
    assert abs(stats.total_return - (-10.0)) < 1e-6


def test_simulate_times_out_after_the_timeout_window():
    level = make_level("1d", [100.0] * 12)
    spec = ExitSpec("none", 0.0, "none", 0.0)

    trades = simulate_trades(level, [True] + [False] * 11, spec, timeout_bars=5)

    assert trades[0].exit_index == 6


def test_drawdown_follows_the_cumulative_trade_curve():
    trades = simulate_trades  # 仅为可读性，下面直接用 stats_from_trades
    from app.engine.advisor.simulate import Trade

    stats = stats_from_trades([Trade(0, 1, 10.0), Trade(2, 3, -30.0), Trade(4, 5, 5.0)], bars=6)

    assert stats.trades == 3
    assert abs(stats.max_drawdown - 30.0) < 1e-6
    assert abs(stats.profit_factor - (15.0 / 30.0)) < 1e-6


# ── 约束与评分 ──────────────────────────────────────────────────────────

def test_constraints_reject_with_readable_reasons():
    constraints = Constraints(min_trades=5, min_win_rate=50, min_frequency=0.0, max_frequency=0.5)

    assert check_constraints(TradeStats(trades=1, wins=1, total_return=10.0, bars=100), constraints) is not None
    assert check_constraints(TradeStats(trades=10, wins=2, total_return=10.0, bars=100), constraints) is not None
    assert check_constraints(TradeStats(trades=10, wins=8, total_return=10.0, bars=10), constraints) is not None
    assert check_constraints(TradeStats(trades=10, wins=8, total_return=-1.0, bars=100), constraints) is not None

    passing = TradeStats(trades=10, wins=8, total_return=10.0, bars=100)
    assert check_constraints(passing, constraints) is None


def test_score_is_zero_without_a_single_positive_window():
    stats = TradeStats(trades=30, wins=20, total_return=30.0, bars=300)
    breakdown = score_windows([-1.0, -2.0, -0.5], stats, Constraints())
    assert breakdown.score == 0.0
    assert breakdown.stability == 0.0


def test_score_rewards_stable_positive_windows():
    stats = TradeStats(trades=30, wins=20, total_return=30.0, bars=300)
    stable = score_windows([2.0, 2.0, 2.0], stats, Constraints())
    lumpy = score_windows([9.0, -3.0, -3.0], stats, Constraints())

    assert stable.score > lumpy.score


# ── 搜索 ────────────────────────────────────────────────────────────────

def _ma_level(closes: list[float], period: int = 5) -> LevelSeries:
    level = make_level("1d", closes)
    values: list[float | None] = []
    for index in range(len(closes)):
        if index < period - 1:
            values.append(None)
        else:
            values.append(sum(closes[index - period + 1:index + 1]) / period)
    level.indicators[indicator_key("ma", {"period": period})] = {"value": values}
    return level


def test_search_ranks_a_trending_rule_first_and_keeps_holdout_after_selection():
    level = _ma_level(trend_closes(300))
    candidate = Candidate(
        id="ma-trend", family="均线", primary_level="1d", entry_level="1d",
        entry=Rule(kind="compare", direction="above", label="价格在均线上方", left_field="close", left_key=None,
                   right_field="value", right_key=indicator_key("ma", {"period": 5})),
        exit=ExitSpec("fixed_pct", 5.0, "fixed_pct", 8.0),
    )
    config = SearchConfig(constraints=Constraints(min_trades=5, min_win_rate=30, min_frequency=0.0, max_frequency=1.0), segments=3)

    outcome = search([candidate], {"1d": level}, config)

    assert outcome.evaluated == 1
    assert len(outcome.results) == 1
    selection_start, selection_end = outcome.selection_bounds
    holdout_start, holdout_end = outcome.holdout_bounds
    assert selection_start == 0
    assert selection_end == holdout_start  # 选定期与留出期首尾相接，不重叠
    assert holdout_end == 300
    # 单边上行 + 价格站上均线 → 选定期应有正收益
    assert outcome.results[0].in_sample.total_return > 0


def test_search_rejects_when_there_are_too_few_trades():
    level = _ma_level(trend_closes(300))
    candidate = Candidate(
        id="rare", family="均线", primary_level="1d", entry_level="1d",
        # 阈值远高于价格 → 永不满足 → 没有交易
        entry=Rule(kind="compare", direction="above", label="不可能成立", left_field="close", left_key=None, right_value=10_000_000.0),
        exit=ExitSpec("fixed_pct", 5.0, "fixed_pct", 8.0),
    )

    outcome = search([candidate], {"1d": level}, SearchConfig(constraints=Constraints(min_trades=5)))

    assert outcome.results == []
    assert len(outcome.rejected) == 1
    assert "交易数不足" in (outcome.rejected[0].rejected_reason or "")


# ── 画像 ────────────────────────────────────────────────────────────────

def test_profile_separates_trend_from_chop():
    trend = [{"open": value, "high": value, "low": value, "close": value, "open_time": index}
             for index, value in enumerate(trend_closes(200))]
    chop = [{"open": value, "high": value, "low": value, "close": value, "open_time": index}
            for index, value in enumerate([100 + 5 * math.sin(index / 2) for index in range(200)])]

    trend_profile = basic_profile("1d", trend)
    chop_profile = basic_profile("1d", chop)

    assert trend_profile.efficiency_ratio > chop_profile.efficiency_ratio
    assert "走势偏趋势" in trend_profile.tags
    assert "走势偏震荡" in chop_profile.tags


def _add_ma(level: LevelSeries, closes: list[float], period: int) -> None:
    values: list[float | None] = []
    for index in range(len(closes)):
        if index < period - 1:
            values.append(None)
        else:
            values.append(sum(closes[index - period + 1:index + 1]) / period)
    level.indicators[indicator_key("ma", {"period": period})] = {"value": values}


def _ma_candidate(period: int, exit_spec: ExitSpec) -> Candidate:
    """价格 vs MA：指标在**右值**侧（曾经的平台判定 bug 就在这里）。"""
    return Candidate(
        id=f"ma-{period}", family="均线", primary_level="1d", entry_level="1d",
        entry=Rule(
            kind="compare", direction="above", label=f"价格在 MA{period} 上方持有",
            left_field="close", left_key=None,
            right_field="value", right_key=indicator_key("ma", {"period": period}),
        ),
        exit=exit_spec,
    )


def test_plateau_detection_covers_rules_whose_indicator_sits_on_the_right_side():
    """相邻参数必须被识别为同一参数平台。

    曾经的实现只看左值 key、且把带参数的 key 放进分组签名，
    导致每个参数自成一组、平台判定恒为 False，于是永远给不出"推荐"。
    """
    closes = trend_closes(300)
    level = make_level("1d", closes)
    close_prices = list(closes)
    # 用真正相邻的周期（M9/M10/M11）：平台判定比较的就是相邻参数
    for period in (9, 10, 11):
        _add_ma(level, close_prices, period)

    exit_spec = ExitSpec("fixed_pct", 5.0, "fixed_pct", 8.0)
    candidates = [_ma_candidate(period, exit_spec) for period in (9, 10, 11)]
    config = SearchConfig(
        constraints=Constraints(min_trades=5, min_win_rate=0, min_frequency=0.0, max_frequency=1.0),
        segments=3,
    )

    outcome = search(candidates, {"1d": level}, config)

    assert len(outcome.results) == 3
    # 单边上行里相邻均线表现接近 → 应当被判为参数平台稳定
    assert any(item.plateau_stable for item in outcome.results), "相邻参数未被识别为参数平台"


def test_budget_is_spread_across_indicator_families():
    """预算截断不能只保注册在前的族。

    MA 有上千个组合，按顺序前缀截断会让其余指标和缠论一个都进不了候选，
    而用户明确要求这些指标都要参与。
    """
    candidates, truncated = build_candidate_space(budget=600)

    assert truncated is True
    families = {item.family for item in candidates}
    # 七个指标族 + 缠论都要有代表
    for expected in ("均线", "MACD", "布林带", "KDJ", "RSI", "成交量", "量柱结构", "筹码分布", "缠论"):
        assert expected in families, f"{expected} 未进入候选空间"


# ── 指标序列与 K 线的时间对齐 ──────────────────────────────────────────

def test_align_values_by_time_keeps_position_when_rows_are_truncated():
    """指标行数少于 K 线时，按时间对齐不能让整条序列平移。

    筹码分布曾经只输出 lookback 行（60）却按行序拼进 500 根的时间轴，
    导致筹码族信号整体错位 440 根。按 time 取则天然对齐，缺的取 None。
    """
    from app.services.advisor_service import align_values_by_time

    times = [100, 200, 300, 400, 500]
    # 指标只覆盖最后两根（模拟缓存裁剪 / lookback 截断）
    values = [{"time": 400, "average_cost": 40.0}, {"time": 500, "average_cost": 50.0}]

    aligned = align_values_by_time(times, values)

    assert aligned["average_cost"] == [None, None, None, 40.0, 50.0]


def test_align_values_by_time_ignores_extra_rows_and_missing_fields():
    from app.services.advisor_service import align_values_by_time

    times = [100, 200]
    values = [
        {"time": 100, "value": 1.0},
        {"time": 200, "value": 2.0, "extra": 9.0},
        {"time": 300, "value": 3.0},  # 不在时间轴上，应被丢弃
    ]

    aligned = align_values_by_time(times, values)

    assert aligned["value"] == [1.0, 2.0]
    # 只在部分行出现的字段也要补齐长度
    assert aligned["extra"] == [None, 9.0]
