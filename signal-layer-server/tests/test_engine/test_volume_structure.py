"""量柱结构：确认门与渲染字段的因果性边界。

这里要锁住两条不同的规则：

1. **决策字段必须因果**：`general_confirmed` / `golden_confirmed` 只在确认根出现。
   曾经的实现把 `general_pillar` / `golden_pillar` 回填到基柱下标，而回测是
   "全量算一次 + 按 time 截断 + 取最后一根"——于是基柱当天就能读到"三天后才知道"
   的确认结果，开仓提前 confirm_bars 根。这两个字段已删除（不在 indicator outputs
   白名单里，也无人消费）。

2. **渲染字段允许回填**：`pillar_kind` / `golden_volume_line` 只被前端用来画
   方框和黄金线，不在 outputs 白名单里（条件编辑器不提供），因此可以把值写回
   它描述的那根量柱上，让方框画在正确的位置。
"""

from app.engine.indicator.volume_structure import VolumeStructureCalculator


def bar(timestamp: int, open_price: float, close: float, low: float, volume: float) -> dict:
    return {
        "open_time": timestamp,
        "open": open_price,
        "high": max(open_price, close) + 0.2,
        "low": low,
        "close": close,
        "volume": volume,
    }


def golden_sample() -> list[dict]:
    return [
        bar(1, 9.8, 10.0, 9.7, 100),
        bar(2, 9.9, 10.0, 9.8, 100),
        bar(3, 10.0, 11.0, 9.9, 220),  # 关键量柱
        bar(4, 11.0, 11.2, 10.8, 160),
        bar(5, 11.1, 11.3, 10.9, 130),
        bar(6, 11.2, 11.4, 11.0, 90),   # 第3根确认：将军柱+黄金柱
        bar(7, 10.0, 9.5, 9.3, 80),     # 跌破基柱最低价
    ]


def test_confirmation_fields_appear_only_at_the_confirm_bar():
    """确认字段不得提前到基柱：基柱当根读不到"已确认"。"""
    result = VolumeStructureCalculator().calculate(golden_sample(), {"lookback": 3})

    # 基柱（下标 2）只能有关键量柱自身的属性，不能有确认结果
    assert result.values[2]["key_pillar"] == 1
    assert "general_confirmed" not in result.values[2]
    assert "golden_confirmed" not in result.values[2]
    # 中间两根同样不能有
    for index in (3, 4):
        assert "general_confirmed" not in result.values[index]
        assert "golden_confirmed" not in result.values[index]
    # 确认根（下标 5）才有
    assert result.values[5]["general_confirmed"] == 1
    assert result.values[5]["golden_confirmed"] == 1
    assert result.values[5]["golden_line"] == 11.0


def test_render_only_fields_may_be_backfilled():
    """渲染字段回填是有意为之：方框/黄金线要画在它描述的那根量柱上。"""
    result = VolumeStructureCalculator().calculate(golden_sample(), {"lookback": 3})

    assert result.values[2]["pillar_kind"] == 3
    assert result.values[2]["golden_volume_line"] == 220
    assert result.values[5]["golden_volume_line"] == 220


def test_decision_fields_are_prefix_causal():
    """决策字段的前缀不变性：跑前 k 根与跑全量，前 k 根必须逐位相同。

    这一条能同时抓住前视与回填——只要某个字段在第 i 行依赖了 i 之后的数据，
    截断重算就会与全量结果不一致。
    """
    calculator = VolumeStructureCalculator()
    full = calculator.calculate(golden_sample(), {"lookback": 3})
    decision_fields = (
        "key_pillar", "key_line", "above_key_line", "key_line_distance_pct",
        "key_line_break", "general_confirmed", "golden_confirmed", "golden_line",
        "above_golden_line", "golden_line_distance_pct", "golden_line_break",
    )

    for length in range(3, len(golden_sample()) + 1):
        prefix = calculator.calculate(golden_sample()[:length], {"lookback": 3})
        assert len(prefix.values) == length, "输出必须与 K 线逐根等长"
        for index in range(length):
            for field in decision_fields:
                assert prefix.values[index].get(field) == full.values[index].get(field), (
                    f"第 {index} 根的 {field} 随后续数据变化（第 {length} 根截断时不一致）"
                )


def test_volume_structure_marks_key_and_golden_line_breaks():
    result = VolumeStructureCalculator().calculate(golden_sample(), {"lookback": 3})

    assert result.values[6]["key_line_break"] == -1
    assert result.values[6]["golden_line_break"] == -1
    assert result.render.window == "sub"
    assert [plot.field for plot in result.render.plots] == ["volume", "golden_volume_line"]
    assert result.render.markers == []


def test_invalid_params_raise_value_error():
    calculator = VolumeStructureCalculator()
    for params in ({"lookback": 2}, {"confirm_bars": 1}, {"key_ratio_min": 1.0}, {"break_tolerance": 0.5}):
        try:
            calculator.calculate(golden_sample(), params)
        except ValueError:
            continue
        raise AssertionError(f"参数 {params} 应当被拒绝")
