"""量价形态的行为测试。

契约测试（test_indicator_contract.py）只保证结构正确（等长、因果、参数有效），
不保证形态真的能被触发——阈值写反、窗口取反这类错误它抓不到。
这里用构造出来的行情把每种形态分别点着一次，并给出"不该触发"的反例。

判定口径（与 calculator 的 docstring 一致）：
- 前高/前低取**当根之前**的窗口（突破要比的是之前的高点）；
- 区间极值取**含当根**的窗口（"创 N 周期新高"天然包含当根）；
- 量能基线取当根之前 baseline_window 根的**中位数**。
"""

from __future__ import annotations

import pytest

from app.engine.indicator.base import auto_discover_indicators, get_registered_indicators

auto_discover_indicators()

DEFAULT_PARAMS = {
    "breakout_window": 20,
    "baseline_window": 20,
    "position_window": 60,
    "rally_streak": 3,
    "volume_ratio_min": 1.5,
    "shrink_max": 0.7,
    "stagnant_pct": 1.0,
    "low_position_pct": 20.0,
}


def make_bars(closes: list[float], volumes: list[float], opens: list[float] | None = None) -> list[dict]:
    """按收盘/成交量构造 K 线；开高低跟着收盘走，避免影线干扰前高前低。"""
    bars: list[dict] = []
    for index, (close, volume) in enumerate(zip(closes, volumes)):
        open_price = opens[index] if opens else (closes[index - 1] if index else close)
        bars.append({
            "open_time": 1_700_000_000_000 + index * 86_400_000,
            "open": open_price,
            "high": max(open_price, close),
            "low": min(open_price, close),
            "close": close,
            "volume": volume,
        })
    return bars


def compute(klines: list[dict], **overrides):
    calculator = get_registered_indicators()["volume_price"]()
    return calculator.calculate(klines, {**DEFAULT_PARAMS, **overrides})


def test_missing_baseline_returns_none_not_zero():
    """预热期必须是 None：填 0 会被条件当成"缩量的真实读数"。"""
    result = compute(make_bars([10.0] * 5, [100.0] * 5))

    for row in result.values:
        assert row["volume_breakout"] is None
        assert row["shrink_pullback"] is None
        assert row["volume_stagnation"] is None
        assert row["climax_top"] is None
        assert row["exhaustion_bottom"] is None
        assert row["bottom_volume"] is None
        assert row["relative_volume"] is None
    # 量价齐升只依赖连续根数：rally_streak=3 时前 3 根预热，之后是真实判定
    assert [row["price_volume_rise"] for row in result.values] == [None, None, None, 0.0, 0.0]
    assert len(result.values) == 5


def test_volume_breakout_needs_both_price_break_and_volume():
    """放量突破：收盘站上前高 **且** 量能高于基线；两者缺一不算。"""
    bars = make_bars([10.0] * 20 + [11.0], [100.0] * 20 + [300.0])
    result = compute(bars, breakout_window=20, baseline_window=20)

    assert result.values[20]["volume_breakout"] == 1.0
    assert result.values[20]["breakout_pct"] == pytest.approx(10.0)
    # 前一根是窗口内最后一根，还没突破
    assert result.values[19]["volume_breakout"] is None

    # 反例一：同样突破前高，但没放量
    quiet = compute(make_bars([10.0] * 20 + [11.0], [100.0] * 21), breakout_window=20, baseline_window=20)
    assert quiet.values[20]["volume_breakout"] == 0.0
    # 反例二：放量但没收在前高之上
    stalled = compute(make_bars([10.0] * 21, [100.0] * 20 + [300.0]), breakout_window=20, baseline_window=20)
    assert stalled.values[20]["volume_breakout"] == 0.0


def test_shrink_pullback_needs_shrink_but_not_breakdown():
    """缩量回调：收跌 + 缩量 + 没跌破参考窗口最低价。"""
    bars = make_bars([10.0] * 20 + [11.0, 10.6], [100.0] * 20 + [300.0, 60.0])
    result = compute(bars, breakout_window=20, baseline_window=20)

    # index 21：收跌（11 → 10.6）、量能 60/100 = 0.6 缩量、收盘 10.6 仍在窗口低点之上
    assert result.values[21]["shrink_pullback"] == 1.0

    # 反例：跌破参考窗口最低价（10.0）就是破位，不是回调
    broken = compute(
        make_bars([10.0] * 20 + [11.0, 9.5], [100.0] * 20 + [300.0, 60.0]),
        breakout_window=20, baseline_window=20,
    )
    assert broken.values[21]["shrink_pullback"] == 0.0


def test_price_volume_rise_requires_both_legs():
    """量价齐升：连续 N 根收涨 **且** 量能逐根放大。"""
    rising = compute(make_bars([10.0, 10.2, 10.5, 10.9], [100.0, 120.0, 150.0, 190.0]), rally_streak=3)
    assert rising.values[3]["price_volume_rise"] == 1.0
    assert rising.values[2]["price_volume_rise"] is None  # 根数不够，属预热

    # 反例：价格连涨但量能没有逐根放大
    flat_volume = compute(make_bars([10.0, 10.2, 10.5, 10.9], [150.0] * 4), rally_streak=3)
    assert flat_volume.values[3]["price_volume_rise"] == 0.0


def test_volume_stagnation_is_volume_up_price_flat():
    """放量滞涨：量能放大但价格几乎没动。"""
    bars = make_bars([10.0] * 20 + [10.05], [100.0] * 20 + [200.0])
    result = compute(bars, stagnant_pct=1.0)

    # -1 表示卖出侧：事件字段的符号即方向（前端 markers 按 val > 0 判买卖）
    assert result.values[20]["volume_stagnation"] == -1.0  # 量能 2.0 倍，涨幅 0.5%

    # 反例：同样放量，但价格涨了 5%，属于正常放量上攻
    surging = compute(make_bars([10.0] * 20 + [10.5], [100.0] * 20 + [200.0]), stagnant_pct=1.0)
    assert surging.values[20]["volume_stagnation"] == 0.0


def test_climax_top_and_exhaustion_bottom_are_symmetric():
    """天量天价 / 地量地价：量与价同时落在区间极值上。"""
    top = compute(
        make_bars([10.0, 10.1, 10.2, 10.15, 10.3], [100.0, 110.0, 120.0, 115.0, 200.0]),
        position_window=5,
    )
    assert top.values[4]["climax_top"] == -1.0
    assert top.values[4]["exhaustion_bottom"] == 0.0

    bottom = compute(
        make_bars([10.5, 10.4, 10.3, 10.35, 10.2], [200.0, 190.0, 180.0, 185.0, 50.0]),
        position_window=5,
    )
    assert bottom.values[4]["exhaustion_bottom"] == 1.0
    assert bottom.values[4]["climax_top"] == 0.0

    # 反例：量创了新高，但价格没创新高（只有量，没有价）
    volume_only = compute(
        make_bars([10.0, 10.1, 10.2, 10.3, 10.25], [100.0, 110.0, 120.0, 115.0, 200.0]),
        position_window=5,
    )
    assert volume_only.values[4]["climax_top"] == 0.0


def test_bottom_volume_needs_deep_drawdown_and_up_bar():
    """底部放量：距区间高点回撤够深时放量收阳。"""
    closes = [20.0] * 6 + [19.0, 18.0, 17.0, 12.0]
    opens = [20.0] * 6 + [19.0, 18.0, 17.0, 11.5]
    bars = make_bars(closes, [100.0] * 9 + [250.0], opens=opens)
    result = compute(bars, position_window=10, low_position_pct=20.0, baseline_window=5)

    # 距区间高点 20.0 回撤 40%，量能 2.5 倍，且收阳
    assert result.values[9]["bottom_volume"] == 1.0
    assert result.values[9]["drawdown_pct"] == pytest.approx(40.0)

    # 反例：同样放量，但没有深度回撤（离高点只有 5%）
    shallow = compute(
        make_bars([20.0] * 9 + [19.0], [100.0] * 9 + [250.0]),
        position_window=10, low_position_pct=20.0, baseline_window=5,
    )
    assert shallow.values[9]["bottom_volume"] == 0.0


def test_render_marks_the_chartable_forms_on_the_price_chart():
    """主图只标 4 个值得看图形态，买卖方向由字段符号决定。

    标记挂在 candlestick series 上（走价格轴），所以它必然与副图那根量柱
    对齐在同一根 K 线——这是"量价"在图上要读出来的东西。
    """
    result = compute(make_bars([10.0] * 30, [100.0] * 30))

    assert result.render is not None
    # 量能本身画在副图，标记落在主图
    assert result.render.window == "sub"
    by_field = {marker.field: marker for marker in result.render.markers}
    assert list(by_field) == ["volume_breakout", "bottom_volume", "volume_stagnation", "climax_top"]
    # 买入侧沿用阳红、预警侧沿用阴绿（与图表的国内配色一致）
    assert by_field["volume_breakout"].buy_label == "放量突破"
    assert by_field["volume_breakout"].buy_color == "#ff5b62"
    assert by_field["bottom_volume"].buy_label == "底部放量"
    assert by_field["volume_stagnation"].sell_label == "放量滞涨"
    assert by_field["climax_top"].sell_label == "天量天价"
    assert by_field["climax_top"].sell_color == "#2fc58d"
    # 两个 label 都得是中文：留默认的 BUY/SELL 就有把英文漏到图上的风险
    for marker in result.render.markers:
        assert marker.buy_label not in ("", "BUY")
        assert marker.sell_label not in ("", "SELL")
    # 中性形态不上图：全标上去箭头会盖满 K 线，它们只作为策略条件可用
    assert not ({"shrink_pullback", "price_volume_rise", "exhaustion_bottom"} & set(by_field))


def test_volume_bars_carry_the_up_down_flag_used_for_coloring():
    """副图量柱按当日阴阳着红绿，前端凭 is_up 上色，所以每根都要带。"""
    result = compute(make_bars([10.0, 9.6], [100.0, 90.0], opens=[10.0, 10.0]))

    assert result.values[0]["is_up"] == 1.0
    assert result.values[1]["is_up"] == 0.0


@pytest.mark.parametrize("params", [
    {"breakout_window": 1},
    {"baseline_window": 1},
    {"position_window": 1},
    {"rally_streak": 1},
    {"volume_ratio_min": 1.0},
    {"shrink_max": 1.5},
    {"stagnant_pct": -1.0},
    {"low_position_pct": 100.0},
])
def test_invalid_params_raise_value_error(params):
    """非法参数必须是 ValueError，接口据此回 invalid_parameters。"""
    with pytest.raises(ValueError):
        compute(make_bars([10.0] * 30, [100.0] * 30), **params)
