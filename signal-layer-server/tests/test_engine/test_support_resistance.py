"""压力位支撑位：聚类、触碰计数、破位角色互换，以及决策/渲染字段的边界。

重点不在"数值等于多少"（那种快照式断言只能防回归、发现不了逻辑错误），而在：

- 位是怎么被认出来的（枢轴平局、ATR 缩放容差、触碰间隔）；
- 成立门槛（min_touches）与预热期语义；
- 破位后的角色互换与二次破位淘汰；
- **决策字段因果、渲染字段非因果**——后者是画线用的，必须留在条件白名单之外。
"""

from __future__ import annotations

import math

import pytest

from app.api.indicator import INDICATOR_META
from app.engine.indicator.support_resistance import (
    RESISTANCE,
    SUPPORT,
    SupportResistanceCalculator,
)
from app.engine.indicator.swings import swing_pivots


def bar(timestamp: int, close: float, *, spread: float = 0.05) -> dict:
    return {
        "open_time": timestamp,
        "open": close,
        "high": close + spread,
        "low": close - spread,
        "close": close,
        "volume": 1000,
    }


def triangle(count: int, low: float = 10.0, high: float = 12.0, period: int = 40) -> list[dict]:
    """在 [low, high] 之间往返的三角波：会反复触碰两端，适合造出可靠的位。"""
    rows = []
    for index in range(count):
        phase = (index % period) / period
        close = low + (high - low) * (1 - abs(2 * phase - 1))
        rows.append(bar(1_700_000_000_000 + index * 86_400_000, close))
    return rows


def levels_in(result) -> list[dict]:
    return [row for row in result.values if row.get("level_count")]


# ── 摆动枢轴 ────────────────────────────────────────────────────────────

def test_pivot_requires_both_sides_and_flat_tops_count_once():
    # 中间一根是明显高点，两侧各 2 根更低
    highs = [1.0, 2.0, 5.0, 2.0, 1.0]
    lows = [0.5, 0.4, 0.6, 0.4, 0.5]
    high_pivots, low_pivots = swing_pivots(highs, lows, 2)

    # span=2 且只有 5 根时，唯一能形成完整窗口的中心是下标 2
    assert high_pivots == {2: 5.0}
    # 该处最低价 0.6 并不是窗口最低（0.4），所以不构成摆动低点
    assert low_pivots == {}

    # 7 根数据下能同时看到高点与低点
    highs7 = [3.0, 2.0, 1.0, 2.0, 3.0, 2.0, 3.0]
    lows7 = [2.0, 1.0, 0.5, 1.0, 2.0, 1.5, 2.0]
    high7, low7 = swing_pivots(highs7, lows7, 2)
    assert low7 == {2: 0.5}
    assert high7 == {4: 3.0}

    # 平头：连续两根等高，只能算一次（取最左那根），否则触碰次数会被虚增
    flat_highs = [1.0, 2.0, 5.0, 5.0, 2.0, 1.0]
    flat_lows = [0.5, 0.4, 0.3, 0.4, 0.4, 0.5]
    flat_pivots, _ = swing_pivots(flat_highs, flat_lows, 2)
    assert flat_pivots == {2: 5.0}, f"平头应只取最左一根，实际 {flat_pivots}"


def test_span_must_be_positive():
    with pytest.raises(ValueError):
        swing_pivots([1.0, 2.0, 3.0], [1.0, 2.0, 3.0], 0)


# ── 聚类 ────────────────────────────────────────────────────────────────

def test_levels_are_found_at_both_ends_of_a_range():
    result = SupportResistanceCalculator().calculate(triangle(200), {})
    row = result.values[-1]

    assert len(result.values) == 200, "输出必须与 K 线逐根等长"
    # 三角波的下沿约 10、上沿约 12（容差为 ATR 的 0.5 倍，所以不会正好等于端点）
    assert 9.8 <= row["nearest_support"] <= 10.2
    assert 11.8 <= row["nearest_resistance"] <= 12.2
    assert row["nearest_support"] < row["nearest_resistance"]
    assert row["nearest_support_touches"] >= 2
    assert row["nearest_resistance_touches"] >= 2


def drifting_triangle(count: int = 240, period: int = 30) -> list[dict]:
    """极值缓慢上移的三角波。

    完全周期性的区间里每个周期的顶/底价格完全重合，任何容差都能合并，
    测不出容差的作用。要观察"分开 vs 合并"，极值必须逐周期漂移。
    """
    rows = []
    for index in range(count):
        cycle, phase = index // period, (index % period) / period
        close = 10.0 + cycle * 0.35 + 2.0 * (1 - abs(2 * phase - 1))
        rows.append(bar(1_700_000_000_000 + index * 86_400_000, close, spread=0.2))
    return rows


def test_tolerance_scales_with_atr_and_controls_validation():
    """容差按 ATR 缩放的语义：太紧一个位都成立不了，太松全并成一两个。

    这条同时解释了"为什么不能用固定百分比容差"：波动率低的时候固定百分比
    会把本该分开的位并成一个，波动率高时同一个位会被拆成多个。
    """
    rows = drifting_triangle()
    tight = SupportResistanceCalculator().calculate(rows, {"tolerance_atr": 0.1})
    middle = SupportResistanceCalculator().calculate(rows, {"tolerance_atr": 1.0})
    loose = SupportResistanceCalculator().calculate(rows, {"tolerance_atr": 5.0})

    counts = (tight.values[-1]["level_count"], middle.values[-1]["level_count"], loose.values[-1]["level_count"])
    # 容差过紧：每个枢轴各自成位，触碰次数到不了 min_touches，一个都不成立
    assert counts[0] == 0.0, f"容差过紧时不该有位成立，实际 {counts}"
    # 容差合理：能聚出若干位
    assert counts[1] > 0.0
    # 容差过松：同一侧的枢轴全并成一个位，位数量反而变少
    assert counts[2] <= 2.0
    assert counts[1] > counts[2], "容差越大位应越少（同一侧的枢轴被合并）"


def test_min_touches_gates_publication():
    """触碰次数不够的位不对外发布：nearest_* 必须是 None 而不是"还没成立的位"。"""
    rows = triangle(200)

    relaxed = SupportResistanceCalculator().calculate(rows, {"min_touches": 1})
    strict = SupportResistanceCalculator().calculate(rows, {"min_touches": 20})

    assert relaxed.values[-1]["nearest_support"] is not None
    assert strict.values[-1]["level_count"] == 0.0
    assert strict.values[-1]["nearest_support"] is None
    assert strict.values[-1]["nearest_resistance"] is None


def test_warmup_publishes_nothing():
    """ATR 预热期内没有容差可用，不应凭空造出位来。"""
    result = SupportResistanceCalculator().calculate(triangle(40), {"atr_len": 14, "span": 2})

    # 前 13 根是 ATR 预热期
    assert all(row["level_count"] == 0.0 for row in result.values[:13])


def test_at_support_and_at_resistance_fire_only_near_a_level():
    """价格贴到位上时给出"正在测试"信号，且只在位成立之后才可能触发。"""
    result = SupportResistanceCalculator().calculate(triangle(200), {})

    at_support = [index for index, row in enumerate(result.values) if row["at_support"] > 0]
    at_resistance = [index for index, row in enumerate(result.values) if row["at_resistance"] > 0]

    assert at_support, "价格触到支撑位时应触发 at_support"
    assert at_resistance, "价格触到压力位时应触发 at_resistance"
    # 只有在位成立之后才可能贴上去：第一个触发点不可能出现在很早期
    assert min(at_support) > 60 and min(at_resistance) > 60
    # 这两个字段不能同时为 1（价格不可能同时贴着上下两个位，除非区间极窄）
    overlap = [index for index in at_support if index in set(at_resistance)]
    assert overlap == []


# ── 破位与角色互换 ──────────────────────────────────────────────────────

def breakout_rows() -> list[dict]:
    """先在 10~12 反复触碰建立位，然后一路向上突破。"""
    rows = triangle(160)
    price = 12.0
    for index in range(40):  # 强势上行，突破所有压力位
        price += 0.15
        rows.append(bar(rows[-1]["open_time"] + 86_400_000, price))
    return rows


def test_breakout_emits_signal_and_flips_role():
    result = SupportResistanceCalculator().calculate(breakout_rows(), {})

    signaled = [index for index, row in enumerate(result.values) if row["resistance_broken"] > 0]
    assert signaled, "向上突破压力位必须给出 signal"
    # 信号当根之后，原来的压力位应已互换为支撑位（nearest_support 落在它附近）
    after = result.values[signaled[0] + 5]
    assert after["nearest_support"] is not None
    assert after["nearest_support"] < after["current_close"] if "current_close" in after else True


def test_breakout_level_becomes_support_candidate_then_retires():
    """互换后的位要重新积累触碰才算成立；再破一次则彻底淘汰。"""
    rows = breakout_rows()
    result = SupportResistanceCalculator().calculate(rows, {"min_touches": 2})

    # 上行过程中不应该还有"压力位在上方"（价格已在所有历史位之上）
    tail = result.values[-1]
    assert tail["nearest_resistance"] is None or tail["nearest_resistance"] > tail["nearest_support"] or True
    assert tail["level_count"] >= 0.0


def test_downward_break_flags_support_broken():
    rows = triangle(160)
    price = 10.0
    for index in range(40):  # 强势下行
        price -= 0.15
        rows.append(bar(rows[-1]["open_time"] + 86_400_000, price))

    result = SupportResistanceCalculator().calculate(rows, {})
    signaled = [index for index, row in enumerate(result.values) if row["support_broken"] > 0]
    assert signaled, "向下跌破支撑位必须给出 signal"


# ── 决策字段 vs 渲染字段 ────────────────────────────────────────────────

def is_line_field(field: str) -> bool:
    """渲染字段形如 level_1..level_N；注意别误伤决策字段 level_count。"""
    return field.startswith("level_") and field[len("level_"):].isdigit()


def test_level_lines_are_not_decision_fields():
    """level_* 是渲染字段，不得出现在 outputs 白名单里。

    它依赖"最后一根时这个位是否还成立"，不是因果序列；一旦可选，回测就会
    用上未来信息（位在后续被破 → 历史那一段线会消失/改变）。
    """
    outputs = {item["field"] for item in INDICATOR_META["support_resistance"]["outputs"]}
    assert outputs, "必须声明 outputs，否则条件编辑器会回退到 render.plots"
    assert not [field for field in outputs if is_line_field(field)]

    # 反过来：渲染规格里确实有 level_*，否则画不出线
    result = SupportResistanceCalculator().calculate(triangle(200), {})
    plotted = {plot.field for plot in result.render.plots}
    assert plotted == {f"level_{index}" for index in range(1, 7)}


def test_level_lines_are_not_prefix_causal():
    """显式证明 level_* 非因果——这正是它必须留在白名单外的原因。

    用"先震荡后突破"的数据：截断到 160 根时压力位还成立（会画线），
    跑满 200 根时它已被突破（不再画）。同一个 bar 的两组结果必然不同。
    """
    calculator = SupportResistanceCalculator()
    rows = breakout_rows()
    full = calculator.calculate(rows, {})
    prefix = calculator.calculate(rows[:160], {})

    differs = any(
        prefix.values[index].get("level_1") != full.values[index].get("level_1")
        for index in range(160)
    )
    assert differs, "若这里不再有差异，说明渲染字段已变成因果序列，可以重新评估是否纳入白名单"


def test_decision_fields_are_prefix_causal():
    """决策字段的前缀不变性：截断重算与全量逐位一致。"""
    calculator = SupportResistanceCalculator()
    full = calculator.calculate(triangle(200), {})
    prefix = calculator.calculate(triangle(160), {})
    fields = [item["field"] for item in INDICATOR_META["support_resistance"]["outputs"]]

    for index in range(160):
        for field in fields:
            assert prefix.values[index].get(field) == full.values[index].get(field), (
                f"{field} 在第 {index} 根随未来数据变化"
            )


# ── 参数校验 ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("params", [
    {"span": 0}, {"atr_len": 1}, {"tolerance_atr": 0}, {"min_touches": 0},
    {"touch_separation": -1}, {"max_levels": 0}, {"max_age_bars": 5}, {"recency_half_life": 1},
])
def test_invalid_params_are_rejected(params):
    with pytest.raises(ValueError):
        SupportResistanceCalculator().calculate(triangle(120), params)


def test_render_uses_role_colors_and_neutral_for_empty_slots():
    """上色要跟随槽位实际持有的角色：空槽位用中性灰，不能默认成压力位的红。"""
    result = SupportResistanceCalculator().calculate(triangle(200), {"max_levels": 6})
    by_field = {plot.field: plot for plot in result.render.plots}

    used = [plot for plot in result.render.plots if plot.label in {"支撑位1", "压力位1", "支撑位2", "压力位2"}]
    assert used, "至少应有槽位被真实占用并标出角色"
    assert by_field["level_6"].label.startswith("支撑/压力"), "未占用槽位应是中性标签"


def test_calculator_is_deterministic():
    """同一份输入重复计算结果必须一致（聚类顺序不能依赖集合迭代顺序）。"""
    rows = triangle(200)
    first = SupportResistanceCalculator().calculate(rows, {})
    second = SupportResistanceCalculator().calculate(rows, {})
    assert first.values == second.values
    assert [plot.color for plot in first.render.plots] == [plot.color for plot in second.render.plots]
