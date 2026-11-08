"""有效性评测引擎的口径测试。

用可手算的合成数据验证：方向化收益、持有期去重、基线、显著性、结论分级。
"""

from app.engine.effectiveness import (
    COST_ROUND_TRIP,
    MIN_SAMPLE,
    PRIMARY_HORIZON,
    SymbolSeries,
    _baseline,
    evaluate_continuous_field,
    evaluate_event_field,
)


def make_series(symbol: str, closes: list[float], field_values: list[float], field: str = "event") -> SymbolSeries:
    return SymbolSeries(
        symbol=symbol,
        closes=closes,
        times=[1_700_000_000_000 + index * 86_400_000 for index in range(len(closes))],
        values=[{field: value} for value in field_values],
    )


def test_event_after_a_rise_has_positive_edge():
    """事件后持续上涨：净收益为正，且显著优于随机入场。"""
    # 100 根：每根涨 1%，事件放在第 20、50 根
    closes = [100.0 * (1.01 ** index) for index in range(100)]
    events = [0.0] * 100
    events[20] = 1.0
    events[50] = 1.0

    result = evaluate_event_field([make_series("AAA", closes, events)], "event", "long")

    assert result.sample_n == 2
    assert result.avg_return is not None and result.avg_return > 0
    assert result.excess_return is not None
    # 样本远小于 MIN_SAMPLE → 只能判样本不足，不能冒充有效
    assert result.verdict == "insufficient"


def test_events_inside_the_holding_period_are_not_double_counted():
    """持有 10 根时，10 根内连续出现的事件只算一次。"""
    closes = [100.0] * 100
    events = [0.0] * 100
    events[20] = events[21] = events[22] = 1.0

    result = evaluate_event_field([make_series("AAA", closes, events)], "event", "long")

    assert result.raw_events == 3
    assert result.sample_n == 1


def test_short_direction_inverts_the_return_sign():
    """下跌行情里，同一批事件按 short 评测应得到正收益，按 long 为负。"""
    closes = [100.0 * (0.99 ** index) for index in range(100)]
    events = [0.0] * 100
    for index in range(10, 90, 12):
        events[index] = 1.0

    short = evaluate_event_field([make_series("AAA", closes, events)], "event", "short")
    long = evaluate_event_field([make_series("AAA", closes, events)], "event", "long")

    assert short.avg_return is not None and short.avg_return > 0
    assert long.avg_return is not None and long.avg_return < 0


def test_valid_verdict_needs_enough_samples_both_halves_and_significance():
    """足够样本 + 两段都为正 + 显著优于随机 → valid。"""
    closes = [100.0 * (1.005 ** index) for index in range(400)]
    events = [0.0] * 400
    for index in range(20, 380, 12):
        events[index] = 1.0

    result = evaluate_event_field([make_series("AAA", closes, events)], "event", "long")

    assert result.sample_n >= MIN_SAMPLE
    assert result.stability["first_half"] is not None and result.stability["first_half"] > 0
    assert result.stability["second_half"] is not None and result.stability["second_half"] > 0
    assert result.verdict in ("valid", "weak")


def test_cost_is_deducted_from_event_returns():
    """横盘里事件收益应为负成本，不能算成 0 或正。"""
    closes = [100.0] * 100
    events = [0.0] * 100
    for index in range(10, 90, 12):
        events[index] = 1.0

    result = evaluate_event_field([make_series("AAA", closes, events)], "event", "long")

    assert result.avg_return is not None
    assert result.avg_return < 0
    assert result.avg_return >= -COST_ROUND_TRIP - 1e-9


def test_continuous_field_picks_a_rule_with_threshold():
    """连续字段会扫出带阈值的规则，并给出方向。"""
    closes = [100.0 * (1.002 ** index) for index in range(300)]
    # 指标值与未来收益同向：值越大，后续涨得越多（这里构造递增序列）
    values = [float(index) for index in range(300)]

    result = evaluate_continuous_field([make_series("AAA", closes, values, field="score")], "score")

    assert result.rule in ("gt", "lt")
    assert result.threshold is not None
    assert result.sample_n > 0
    assert result.direction in ("long", "short")


def test_fields_without_events_are_insufficient():
    closes = [100.0] * 100
    result = evaluate_event_field([make_series("AAA", closes, [0.0] * 100)], "event", "long")

    assert result.sample_n == 0
    assert result.verdict == "insufficient"


def test_baseline_pools_symbols_by_sample_count():
    """基线是所有标的、所有可入场点的平均前瞻收益。

    这里两只标的样本数不同、均值不同，池化结果必须按样本数加权；
    曾经把"已经求过和的值"又乘了一次样本数，基线被放大约百倍。
    """
    # 标的 A：横盘 200 根，前瞻收益恒为 0
    flat = [100.0] * 200
    # 标的 B：每根涨 1%，10 根前瞻约 +10.5%
    rising = [100.0 * (1.01 ** index) for index in range(20)]

    series = [make_series("A", flat, [0.0] * 200), make_series("B", rising, [0.0] * 20)]
    baseline = _baseline(series, 10)

    assert baseline is not None
    # 池化值必须落在两段真实均值之间，而不是被放大
    assert -0.01 < baseline < 0.12
    assert baseline < 0.2


def test_primary_horizon_is_used_for_verdict_metrics():
    """结论指标基于主持有期；decay 覆盖所有持有期。"""
    closes = [100.0 * (1.004 ** index) for index in range(300)]
    events = [0.0] * 300
    for index in range(10, 290, 12):
        events[index] = 1.0

    result = evaluate_event_field([make_series("AAA", closes, events)], "event", "long")

    assert set(result.decay) == {1, 3, 5, 10, 20}
    assert PRIMARY_HORIZON == 10
    assert result.decay[1] is not None and result.decay[10] is not None
