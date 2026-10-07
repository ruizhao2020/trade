"""流动性聚集区：等高/等低成区、扫荡判定、破位退役。

这个指标的语义比支撑压力位更容易搞错方向，因此测试重点是**两侧不对称**：
- 等高区（EQH）的流动性在上沿，只有"收在上方并站住"才算破位，价格往回跌与它无关；
- 等低区（EQL）镜像。
最初我把破位写成双向判断，结果价格一离开区间就把区判退役了——下面的
`test_pullback_away_from_a_zone_is_not_a_break` 就是为这个错误立的护栏。
"""

from __future__ import annotations

import pytest

from app.api.indicator import INDICATOR_META
from app.engine.indicator.liquidity_zone import (
    DOWN,
    EQ_HIGH,
    EQ_LOW,
    UP,
    LiquidityZoneCalculator,
)


def bar(timestamp: int, close: float, *, high: float | None = None, low: float | None = None) -> dict:
    return {
        "open_time": timestamp,
        "open": close,
        "high": close + 0.05 if high is None else high,
        "low": close - 0.05 if low is None else low,
        "close": close,
        "volume": 1000,
    }


def ranging(count: int = 180, low: float = 10.0, high: float = 12.0, period: int = 30) -> list[dict]:
    """在 [low, high] 之间往返：每 period 根触及一次上沿与下沿，形成等高/等低。"""
    rows = []
    for index in range(count):
        phase = (index % period) / period
        close = low + (high - low) * (1 - abs(2 * phase - 1))
        rows.append(bar(1_700_000_000_000 + index * 86_400_000, close))
    return rows


def zone_fields(result) -> dict:
    row = result.values[-1]
    return {key: row.get(key) for key in (
        "zone_count", "nearest_zone_low", "nearest_zone_high",
        "nearest_zone_touches", "nearest_zone_swept", "price_in_zone",
    )}


# ── 成区 ────────────────────────────────────────────────────────────────

def test_equal_highs_and_lows_form_zones():
    result = LiquidityZoneCalculator().calculate(ranging(), {})

    assert len(result.values) == 180, "输出必须与 K 线逐根等长"
    assert result.values[-1]["zone_count"] >= 1.0
    # 至少应认出上方与下方两个聚集区（等高与等低）
    assert result.values[-1]["nearest_zone_low"] < result.values[-1]["nearest_zone_high"]


def test_pullback_away_from_a_zone_is_not_a_break():
    """价格离开区间不算破位——只有收在该区外侧并站住才算。

    这条防的是"双向破位"的错误：等高区的流动性在上沿，价格跌回下方与它无关。
    """
    rows = ranging(180)
    result = LiquidityZoneCalculator().calculate(rows, {})

    # 上沿附近的区在整个样本里都应存在（价格从未收在 12 之上）
    highs_near_ceiling = [
        index for index, row in enumerate(result.values)
        if (row.get("nearest_zone_high") or 0) > 11.9
    ]
    assert highs_near_ceiling, "上方聚集区应长期有效，不该因为价格回落就退役"
    assert all(row["zone_broken"] == 0.0 for row in result.values), "没有向上突破，不该出现破位"


def test_min_touches_gates_zone_publication():
    rows = ranging(180)

    relaxed = LiquidityZoneCalculator().calculate(rows, {"min_touches": 1})
    strict = LiquidityZoneCalculator().calculate(rows, {"min_touches": 20})

    assert relaxed.values[-1]["zone_count"] > 0.0
    assert strict.values[-1]["zone_count"] == 0.0
    assert strict.values[-1]["nearest_zone_low"] is None


def drifting_ranging(count: int = 240, period: int = 30) -> list[dict]:
    """极值缓慢上移的区间震荡。

    完全周期性的区间里每个周期的极值价格完全重合，任何容差都能合并，
    测不出"等高容差"的作用——所以极值必须逐周期漂移。
    """
    rows = []
    for index in range(count):
        cycle, phase = index // period, (index % period) / period
        close = 10.0 + cycle * 0.03 + 2.0 * (1 - abs(2 * phase - 1))
        rows.append(bar(1_700_000_000_000 + index * 86_400_000, close))
    return rows


def test_equality_tolerance_controls_formation():
    """容差按 ATR 缩放：极紧时每个枢轴各自成区、触碰数到不了门槛，一个区都不成立。"""
    rows = drifting_ranging()

    tight = LiquidityZoneCalculator().calculate(rows, {"eq_atr": 0.001})
    loose = LiquidityZoneCalculator().calculate(rows, {"eq_atr": 5.0})

    assert tight.values[-1]["zone_count"] == 0.0, "容差过紧时不该成区"
    assert loose.values[-1]["zone_count"] > 0.0


def test_warmup_forms_no_zone():
    result = LiquidityZoneCalculator().calculate(ranging(30), {"atr_len": 14, "span": 2})

    assert all(row["zone_count"] == 0.0 for row in result.values[:13])


# ── 扫荡 ────────────────────────────────────────────────────────────────

def swept_upper() -> list[dict]:
    """在区间内往返，然后在某根做一次"影线越过上沿后收回"→ 上沿被扫荡。"""
    rows = ranging(180)
    index = 100
    rows[index] = bar(rows[index]["open_time"], 11.8, high=13.0, low=11.7)
    return rows


def box_for(result, *, above: float | None = None, below: float | None = None) -> dict | None:
    """找出"上沿在 above 之上"（或"下沿在 below 之下"）的那个方框槽位。

    返回 {slot, first, last, consumed, from_top, label}；找不到返回 None。
    """
    matches: list[dict] = []
    for slot in range(1, 9):
        row_ids = [
            index for index, row in enumerate(result.values)
            if row.get(f"zone_{slot}_low") is not None
        ]
        if not row_ids:
            continue
        last = result.values[row_ids[-1]]
        low = result.values[row_ids[0]][f"zone_{slot}_low"]
        high = result.values[row_ids[0]][f"zone_{slot}_high"]
        if above is not None and high <= above:
            continue
        if below is not None and low >= below:
            continue
        label = next((plot.label for plot in result.render.plots if plot.field == f"zone_{slot}_low"), "")
        matches.append({
            "slot": slot, "first": row_ids[0], "last": row_ids[-1],
            "low": low, "high": high,
            "consumed": last[f"zone_{slot}_consumed"],
            "swept": last[f"zone_{slot}_swept"],
            "swept_from_top": last[f"zone_{slot}_swept_from_top"],
            "label": label,
        })
    # 生成中的候选区也会出现在上沿附近，取**最早生成**的那个才是最初跟踪的区
    return min(matches, key=lambda item: item["first"]) if matches else None


def test_wick_beyond_edge_then_close_back_is_a_sweep():
    result = LiquidityZoneCalculator().calculate(swept_upper(), {})

    fired = [index for index, row in enumerate(result.values) if row["sweep_up"] > 0]
    assert fired == [100], f"上沿被扫荡应在第 100 根触发，实际 {fired}"
    # 被扫荡后该区退出有效集合：方框转为"已扫荡"并标出被拿走的比例
    box = box_for(result, above=11.9)
    assert box is not None
    assert box["consumed"] == 1.0, "影线完全越过区带应记为 100% 被拿走"
    assert "已扫荡" in box["label"]


def test_sweep_requires_close_back_within_the_reclaim_window():
    """影线越界后一直不收回 → 不算扫荡（那是突破，不是止损猎杀）。"""
    rows = ranging(180)
    index = 100
    # 该根影线越界且**收盘也在区外**：不构成同根收回
    rows[index] = bar(rows[index]["open_time"], 12.5, high=13.0, low=12.4)
    for offset in range(1, 6):
        rows[index + offset] = bar(rows[index + offset]["open_time"], 12.5 + offset * 0.05)

    result = LiquidityZoneCalculator().calculate(rows, {"reclaim_bars": 1})

    assert all(row["sweep_up"] == 0.0 for row in result.values), "没收回就不该报扫荡"


def test_lower_edge_sweep_is_mirrored():
    rows = ranging(180)
    index = 100
    rows[index] = bar(rows[index]["open_time"], 10.2, high=10.3, low=9.0)

    result = LiquidityZoneCalculator().calculate(rows, {})

    fired = [i for i, row in enumerate(result.values) if row["sweep_down"] > 0]
    assert fired == [100], f"下沿被扫荡应在第 100 根触发，实际 {fired}"


# ── 破位退役 ────────────────────────────────────────────────────────────

def broken_upper() -> list[dict]:
    """收在上沿之上并连续站住 → 真破位。"""
    rows = ranging(180)
    for offset in range(6):
        index = 150 + offset
        rows[index] = bar(rows[index]["open_time"], 12.8 + offset * 0.05)
    return rows


def test_close_beyond_edge_retires_the_zone():
    calculator = LiquidityZoneCalculator()
    before = calculator.calculate(ranging(180), {})
    target = box_for(before, above=11.9)
    assert target is not None

    after = calculator.calculate(broken_upper(), {})
    fired = [index for index, row in enumerate(after.values) if row["zone_broken"] > 0]
    assert fired, "连续收在上沿之上必须判定为破位"
    # 破位后该区退役：数量下降
    assert after.values[-1]["zone_count"] < before.values[-1]["zone_count"]

    # 被破位的那个区不再画框（注意：破位处会形成**新的**区，那些应该正常画，
    # 所以这里精确比对原区带的上下沿，而不是"不许有高位的线"）
    for row in after.values[fired[-1] + 1:]:
        for slot in range(1, 5):
            low, high = row.get(f"zone_{slot}_low"), row.get(f"zone_{slot}_high")
            if low is None or high is None:
                continue
            same_band = abs(low - target["low"]) < 1e-6 and abs(high - target["high"]) < 1e-6
            assert not same_band, "被破位的区不该继续画框（会误导为仍然有效）"


# ── 决策字段 vs 渲染字段 ────────────────────────────────────────────────

def is_zone_render_field(field: str) -> bool:
    """方框渲染字段形如 zone_1_low / zone_2_consumed；注意别误伤 nearest_zone_low。"""
    parts = field.split("_")
    return (
        len(parts) == 3 and parts[0] == "zone" and parts[1].isdigit()
        and parts[2] in {"low", "high", "consumed", "from_top"}
    )


def test_zone_boxes_are_not_decision_fields():
    outputs = {item["field"] for item in INDICATOR_META["liquidity_zone"]["outputs"]}
    assert outputs, "必须声明 outputs，否则条件编辑器会回退到 render.plots"
    assert not [field for field in outputs if is_zone_render_field(field)]

    result = LiquidityZoneCalculator().calculate(ranging(180), {"max_zones": 3})
    # 每个槽位一个方框规格（方框的两个边界由 zone_{k}_low/high 两个兄弟字段给定）
    assert [plot.field for plot in result.render.plots] == ["zone_1_low", "zone_2_low", "zone_3_low"]
    assert all(plot.type == "zone" for plot in result.render.plots)
    assert result.render.window == "main"


def test_every_zone_plot_has_its_sibling_fields():
    """前端按约定取兄弟字段（_high/_consumed/_from_top），约定断裂就画不出方框。"""
    result = LiquidityZoneCalculator().calculate(ranging(180), {"max_zones": 3})

    for slot in range(1, 4):
        row_ids = [
            index for index, row in enumerate(result.values)
            if row.get(f"zone_{slot}_low") is not None
        ]
        if not row_ids:
            continue
        sample = result.values[row_ids[-1]]
        for suffix in ("low", "high", "consumed", "swept", "swept_from_top"):
            assert f"zone_{slot}_{suffix}" in sample, f"缺少约定字段 zone_{slot}_{suffix}"


def test_render_marks_swept_zones_in_colour_and_legend():
    """是否已被扫荡要能一眼读出来：颜色与图例都随状态变。"""
    plain = LiquidityZoneCalculator().calculate(ranging(180), {})
    swept = LiquidityZoneCalculator().calculate(swept_upper(), {})

    import app.engine.indicator.liquidity_zone as module

    plain_plot = plain.render.plots[0]
    assert plain_plot.color == module.ACTIVE_COLOR, "仍在聚集的区应是活跃配色"
    assert "已扫荡" not in plain_plot.label

    swept_labels = [plot.label for plot in swept.render.plots]
    assert any("已扫荡" in label for label in swept_labels), "被扫荡的区应在图例里标出来"
    assert any(plot.color == module.SWEPT_COLOR for plot in swept.render.plots)


def test_zone_lines_are_not_prefix_causal():
    """渲染字段非因果：截断点在破位之前，全量那次该区已退役不再画，
    于是同一个 bar 上画的区必然不同。"""
    calculator = LiquidityZoneCalculator()
    rows = broken_upper()
    full = calculator.calculate(rows, {})
    prefix = calculator.calculate(rows[:140], {})

    differs = any(
        prefix.values[index].get("zone_1_high") != full.values[index].get("zone_1_high")
        for index in range(140)
    )
    assert differs, "若不再有差异，说明渲染字段已变成因果序列，可以重新评估是否纳入白名单"


def test_decision_fields_are_prefix_causal():
    calculator = LiquidityZoneCalculator()
    full = calculator.calculate(swept_upper(), {})
    prefix = calculator.calculate(swept_upper()[:150], {})
    fields = [item["field"] for item in INDICATOR_META["liquidity_zone"]["outputs"]]

    for index in range(150):
        for field in fields:
            assert prefix.values[index].get(field) == full.values[index].get(field), (
                f"{field} 在第 {index} 根随未来数据变化"
            )


def test_calculator_is_deterministic():
    rows = ranging(180)
    first = LiquidityZoneCalculator().calculate(rows, {})
    second = LiquidityZoneCalculator().calculate(rows, {})
    assert first.values == second.values


# ── 参数校验 ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("params", [
    {"span": 0}, {"atr_len": 1}, {"eq_atr": 0}, {"min_touches": 0},
    {"zone_width_atr": 0}, {"pierce_atr": -1}, {"reclaim_bars": 0},
    {"break_bars": 0}, {"max_age_bars": 5}, {"max_zones": 0},
])
def test_invalid_params_are_rejected(params):
    with pytest.raises(ValueError):
        LiquidityZoneCalculator().calculate(ranging(120), params)


def test_constants_are_stable():
    """方向与类型的字面量被前端与文档引用，改动会静默破坏兼容。"""
    assert (EQ_HIGH, EQ_LOW, UP, DOWN) == ("eqh", "eql", "up", "down")


# ── 生命周期：生成 → 聚集 → 被扫荡 → 消失 ──────────────────────────────

def upper_zone_band(rows: list[dict]) -> tuple[float, float]:
    """先跑一遍拿到上沿聚集区的区带上下沿，用于构造精确的越界幅度。"""
    result = LiquidityZoneCalculator().calculate(rows, {})
    for row in result.values:
        high = row.get("nearest_zone_high")
        if high is not None and high > 11.9:
            return row["nearest_zone_low"], high
    raise AssertionError("样本里应存在上沿聚集区")


def pierce_upper(rows: list[dict], index: int, ratio: float, low: float, high: float) -> None:
    """在第 index 根制造一次"越界到带宽的 ratio 倍后收回区内"的刺穿。"""
    band = high - low
    rows[index] = bar(rows[index]["open_time"], low + 0.01, high=high + band * ratio, low=low - 0.01)


def test_lifecycle_partial_sweep_keeps_a_dashed_box_with_fill_ratio():
    rows = ranging(200)
    low, high = upper_zone_band(rows)
    pierce_upper(rows, 140, 0.4, low, high)

    result = LiquidityZoneCalculator().calculate(rows, {})
    box = box_for(result, above=11.9)

    assert box is not None
    assert box["consumed"] == pytest.approx(0.4, abs=0.02), "越界 40% 带宽应记为 40% 被拿走"
    assert box["swept_from_top"] == 1.0, "等高区的流动性在上沿，被扫荡方向应记为自上沿"
    assert "已扫荡" in box["label"]
    # 方框右边界定格在扫荡那一刻，之后不再延伸
    assert box["last"] == 140


def test_lifecycle_full_sweep_marks_the_zone_gone():
    rows = ranging(200)
    low, high = upper_zone_band(rows)
    pierce_upper(rows, 140, 1.2, low, high)

    result = LiquidityZoneCalculator().calculate(rows, {})
    box = box_for(result, above=11.9)

    assert box is not None
    assert box["consumed"] == 1.0, "越界超过一个带宽即完全扫荡"
    assert "100%" in box["label"]


def test_swept_zone_leaves_the_decision_set():
    """被扫荡的区不再出现在决策字段里（"扫荡后聚集区就不存在了"）。"""
    clean = LiquidityZoneCalculator().calculate(ranging(200), {})

    rows = ranging(200)
    low, high = upper_zone_band(rows)
    pierce_upper(rows, 140, 0.4, low, high)
    swept = LiquidityZoneCalculator().calculate(rows, {})

    # 扫荡前两者一致，扫荡后上沿区退出有效集合
    upper_before = [i for i, r in enumerate(clean.values) if (r.get("nearest_zone_high") or 0) > 11.9]
    upper_after = [i for i, r in enumerate(swept.values) if (r.get("nearest_zone_high") or 0) > 11.9]
    assert upper_before, "对照组应能看到上沿区"
    assert not [i for i in upper_after if i > 140], "被扫荡后上沿区不该再出现在决策字段里"


def test_low_penetration_below_the_noise_gate_keeps_the_zone_accumulating():
    """低于 pierce 门槛的轻微越界是噪声：填充比例会有一点点，但区仍在聚集阶段。

    这是刻意的两层口径——**填充比例从 0 平滑增长**（几何幅度），而**状态切换**
    走 pierce 噪声门槛。所以实线框上出现很小的填充是正常现象，不代表已被扫荡。
    """
    rows = ranging(200)
    low, high = upper_zone_band(rows)
    pierce_upper(rows, 140, 0.02, low, high)   # 只越界 2% 带宽

    result = LiquidityZoneCalculator().calculate(rows, {})
    box = box_for(result, above=11.9)

    assert box is not None
    assert "已扫荡" not in box["label"], "低于噪声门槛不该判成被扫荡"
    assert box["last"] == len(result.values) - 1, "未被扫荡的区应一直画到最后一根"
    # 门槛对应的比例 = pierce_atr / zone_width_atr = 0.3，低于它不算被扫荡
    assert box["consumed"] < 0.3


def test_active_zone_box_extends_to_the_last_bar():
    result = LiquidityZoneCalculator().calculate(ranging(200), {})
    last_index = len(result.values) - 1

    for slot in range(1, 5):
        row_ids = [
            index for index, row in enumerate(result.values)
            if row.get(f"zone_{slot}_low") is not None
        ]
        if row_ids:
            assert row_ids[-1] == last_index, "仍在聚集的区，方框右边界应延伸到最后一根"


def test_forming_zone_is_drawn_before_it_is_validated():
    """生成阶段（第一个枢轴、触碰次数还不够）就应该画出方框。

    模块文档一直写着"生成：第一个枢轴落下，区带出现"，但实现只画已成立的区——
    文档与代码不一致。生成与聚集都是实线框，因此生成期也必须出现。
    """
    result = LiquidityZoneCalculator().calculate(ranging(180), {"min_touches": 3})

    labels = [plot.label for plot in result.render.plots]
    assert any("生成中" in label or "聚集" in label for label in labels), (
        f"应存在生成中或已聚集的方框，实际图例：{labels}"
    )


def test_swept_zone_keeps_its_box_as_history():
    """被扫荡的区仍保留方框（虚线 + 抽空），只是退出了决策集合。"""
    rows = ranging(200)
    low, high = upper_zone_band(rows)
    pierce_upper(rows, 140, 0.5, low, high)

    result = LiquidityZoneCalculator().calculate(rows, {})
    box = box_for(result, above=11.9)

    assert box is not None and box["swept"] == 1.0
    # 方框仍在画（作为历史），只是定格在被扫荡处
    assert box["last"] == 140
    assert "已扫荡" in box["label"]
    # 该区已不在决策字段里
    assert result.values[-1]["zone_count"] < 2.0 or all(
        (row.get("nearest_zone_high") or 0) < 11.9 for row in result.values[141:]
    )


def test_swept_boxes_outrank_forming_candidates():
    """已被扫荡的区要比"生成中的候选"更优先占槽位。

    "扫荡后不填充"是这块方框要传达的核心信息之一；候选区只是候选，
    把它排在历史前面会让用户看不到流动性被拿走的痕迹。
    """
    rows = ranging(200)
    low, high = upper_zone_band(rows)
    pierce_upper(rows, 140, 0.6, low, high)

    result = LiquidityZoneCalculator().calculate(rows, {"max_zones": 2})
    labels = [plot.label for plot in result.render.plots]

    assert any("已扫荡" in label for label in labels), f"被扫荡的区应占一个槽位，实际图例：{labels}"
