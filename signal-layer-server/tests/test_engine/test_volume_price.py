"""量价形态的行为测试。

契约测试（test_indicator_contract.py）只保证结构正确（等长、因果、参数有效），
不保证形态真的能被触发——阈值写反、窗口取反这类错误它抓不到。
这里用构造出来的行情把每种形态分别点着一次，并给出"不该触发"的反例。

判定口径（与 calculator 的 docstring 一致）：
- 前高/前低取**当根之前**的 breakout_window 根 K 线（突破要比的是之前的高点）；
- 量能基线取当根之前 baseline_window 根 K 线成交量的**中位数**；
- 区间极值/回撤取**含当根**的 position_window 根 K 线；
- 缩量回调、量价齐升、地量地价按**连续 consecutive_bars 根 K 线**判定。
"""

from __future__ import annotations

import pytest

from app.engine.indicator.base import auto_discover_indicators, get_registered_indicators

auto_discover_indicators()

DEFAULT_PARAMS = {
    "breakout_window": 20,
    "baseline_window": 20,
    "position_window": 60,
    "consecutive_bars": 3,
    "volume_ratio_min": 1.5,
    "shrink_max": 0.7,
    "stagnant_pct": 1.0,
    "stagnant_max_drawdown_pct": 10.0,
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
    # 量价齐升只依赖连续根数：consecutive_bars=3 时前 3 根预热，之后是真实判定
    assert [row["price_volume_rise"] for row in result.values] == [None, None, None, 0.0, 0.0]
    assert len(result.values) == 5


def test_volume_breakout_needs_both_price_break_and_volume():
    """放量突破：收盘站上前高 **且** 量能高于基线；两者缺一不算。"""
    bars = make_bars([10.0] * 20 + [11.0], [100.0] * 20 + [300.0])
    result = compute(bars)

    assert result.values[20]["volume_breakout"] == 1.0
    assert result.values[20]["breakout_pct"] == pytest.approx(10.0)
    # 前一根还没凑够 20 根历史，属预热（None 而不是 0）
    assert result.values[19]["volume_breakout"] is None

    # 反例一：同样突破前高，但没放量
    quiet = compute(make_bars([10.0] * 20 + [11.0], [100.0] * 21))
    assert quiet.values[20]["volume_breakout"] == 0.0
    # 反例二：放量但没收在前高之上
    stalled = compute(make_bars([10.0] * 21, [100.0] * 20 + [300.0]))
    assert stalled.values[20]["volume_breakout"] == 0.0


def test_shrink_pullback_requires_consecutive_bars():
    """缩量回调：连续 consecutive_bars 根**逐根走低且逐根缩量**，最后一根仍不破前低。

    单根收跌缩量不算——那只是某一根量小，不是一段回调。
    """
    closes = [10.0] * 19 + [11.0, 10.7, 10.4, 10.2]
    volumes = [100.0] * 20 + [60.0, 60.0, 60.0]
    result = compute(make_bars(closes, volumes))

    # 第 21 根（下标 21）时只有两根满足"逐根走低"，第 3 根还没出来
    assert result.values[21]["shrink_pullback"] == 0.0
    # 第 22 根：20→21→22 三根逐根走低、每根量能 0.6 倍、且收盘 10.2 仍在前低 10.0 之上
    assert result.values[22]["shrink_pullback"] == 1.0

    # 反例：同样是三根走低缩量，但最后一根跌破了前低 → 是破位，不是回调
    broken = compute(make_bars([10.0] * 19 + [11.0, 10.7, 10.4, 9.5], [100.0] * 20 + [60.0, 60.0, 60.0]))
    assert broken.values[22]["shrink_pullback"] == 0.0


def test_price_volume_rise_requires_both_legs():
    """量价齐升：连续 consecutive_bars 根收涨 **且** 量能逐根放大。"""
    rising = compute(make_bars([10.0, 10.2, 10.5, 10.9], [100.0, 120.0, 150.0, 190.0]))
    assert rising.values[3]["price_volume_rise"] == 1.0
    assert rising.values[2]["price_volume_rise"] is None  # 根数不够，属预热

    # 反例：价格连涨但量能没有逐根放大
    flat_volume = compute(make_bars([10.0, 10.2, 10.5, 10.9], [150.0] * 4))
    assert flat_volume.values[3]["price_volume_rise"] == 0.0


def test_volume_stagnation_requires_a_high_position():
    """放量滞涨：量放大而价格没动，**且处在相对高位**。

    没有高位这条约束时，下跌途中的放量横盘（承接/换手）会被误判成顶部预警。
    """
    flat_high = compute(make_bars([10.0] * 20 + [10.05], [100.0] * 20 + [200.0]), position_window=10)
    # 贴在高位（回撤 0%）、量能 2 倍、涨幅 0.5%
    assert flat_high.values[20]["volume_stagnation"] == -1.0

    # 反例一：量能没放大
    quiet = compute(make_bars([10.0] * 20 + [10.05], [100.0] * 21), position_window=10)
    assert quiet.values[20]["volume_stagnation"] == 0.0

    # 反例二：同样放量滞涨，但已经跌掉三分之一（回撤 33% > 高位上限 10%）→ 不是顶部预警
    dropped = compute(make_bars([30.0] * 19 + [20.0, 20.0], [100.0] * 19 + [100.0, 200.0]), position_window=10)
    assert dropped.values[20]["volume_stagnation"] == 0.0
    # 把高位上限放宽到 50%，同一根就会被认成滞涨 → 证明限制生效的是这一条
    relaxed = compute(
        make_bars([30.0] * 19 + [20.0, 20.0], [100.0] * 19 + [100.0, 200.0]),
        position_window=10, stagnant_max_drawdown_pct=50.0,
    )
    assert relaxed.values[20]["volume_stagnation"] == -1.0


def test_climax_top_is_sell_side_and_symmetric_to_exhaustion():
    """天量天价：量与价同时创出位置窗口极值，取 -1（卖出侧）。"""
    top = compute(
        make_bars([10.0, 10.1, 10.2, 10.15, 10.3], [100.0, 110.0, 120.0, 115.0, 200.0]),
        position_window=5,
    )
    assert top.values[4]["climax_top"] == -1.0

    # 反例：量创了新高，但价格没创新高（只有量，没有价）
    volume_only = compute(
        make_bars([10.0, 10.1, 10.2, 10.3, 10.25], [100.0, 110.0, 120.0, 115.0, 200.0]),
        position_window=5,
    )
    assert volume_only.values[4]["climax_top"] == 0.0


def test_exhaustion_bottom_requires_sustained_shrink_at_a_low_position():
    """地量地价：连续 consecutive_bars 根都缩量、且都趴在位置窗口的低位。

    不是"当根量创窗口新低"——地量是连续一段时间的量能枯竭。
    注意基线窗口要够长（这里 10 根）：若基线窗口只有 5 根、其中 3 根是低量柱，
    基线本身会被拖到低位，当根就不算"缩量"了。
    """
    closes = [20.0] * 8 + [12.0] * 5
    volumes = [100.0] * 8 + [40.0] * 5
    result = compute(
        make_bars(closes, volumes),
        position_window=10, baseline_window=10, low_position_pct=20.0,
    )

    # 下标 11 的三根里还有一根没有量能基线（预热），连续段不成立
    assert result.values[11]["exhaustion_bottom"] == 0.0
    # 下标 12：10/11/12 三根都缩量（0.4 倍）且都距高点回撤 40%
    assert result.values[12]["exhaustion_bottom"] == 1.0

    # 反例：低位但不缩量（量能没有枯竭）
    noisy = compute(
        make_bars(closes, [100.0] * 8 + [200.0] * 5),
        position_window=10, baseline_window=10, low_position_pct=20.0,
    )
    assert noisy.values[12]["exhaustion_bottom"] == 0.0

    # 反例：缩量但不在低位（只是普通回调）
    high = compute(
        make_bars([20.0] * 13, [100.0] * 8 + [40.0] * 5),
        position_window=10, baseline_window=10, low_position_pct=20.0,
    )
    assert high.values[12]["exhaustion_bottom"] == 0.0


def test_bottom_volume_needs_deep_drawdown_and_up_bar():
    """底部放量：距区间高点回撤够深时放量收阳。"""
    closes = [20.0] * 6 + [19.0, 18.0, 17.0, 12.0]
    opens = [20.0] * 6 + [19.0, 18.0, 17.0, 11.5]
    bars = make_bars(closes, [100.0] * 9 + [250.0], opens=opens)
    result = compute(bars, position_window=10, low_position_pct=20.0, baseline_window=5)

    assert result.values[9]["bottom_volume"] == 1.0
    assert result.values[9]["drawdown_pct"] == pytest.approx(40.0)

    # 反例：同样放量，但没有深度回撤（离高点只有 5%）
    shallow = compute(
        make_bars([20.0] * 9 + [19.0], [100.0] * 9 + [250.0]),
        position_window=10, low_position_pct=20.0, baseline_window=5,
    )
    assert shallow.values[9]["bottom_volume"] == 0.0


def test_all_seven_forms_are_marked_on_the_price_chart():
    """七个形态都要在主图标记；买卖侧由字段符号与配色区分。"""
    result = compute(make_bars([10.0] * 30, [100.0] * 30))

    assert result.render is not None
    assert result.render.window == "sub"  # 量能画在副图
    by_field = {marker.field: marker for marker in result.render.markers}
    assert list(by_field) == [
        "volume_breakout", "shrink_pullback", "price_volume_rise",
        "bottom_volume", "exhaustion_bottom",
        "volume_stagnation", "climax_top",
    ]
    # 买入侧沿用阳红、预警侧沿用阴绿（与图表的国内配色一致）
    for field in ["volume_breakout", "shrink_pullback", "price_volume_rise", "bottom_volume", "exhaustion_bottom"]:
        assert by_field[field].buy_color == "#ff5b62"
    for field in ["volume_stagnation", "climax_top"]:
        assert by_field[field].sell_color == "#2fc58d"
    # 两个 label 都得是中文：留默认的 BUY/SELL 就有把英文漏到图上的风险
    for marker in result.render.markers:
        assert marker.buy_label not in ("", "BUY"), marker.field
        assert marker.sell_label not in ("", "SELL"), marker.field


def test_volume_bars_carry_the_up_down_flag_used_for_coloring():
    """副图量柱按当日阴阳着红绿，前端凭 is_up 上色，所以每根都要带。"""
    result = compute(make_bars([10.0, 9.6], [100.0, 90.0], opens=[10.0, 10.0]))

    assert result.values[0]["is_up"] == 1.0
    assert result.values[1]["is_up"] == 0.0


@pytest.mark.parametrize("params", [
    {"breakout_window": 1},
    {"baseline_window": 1},
    {"position_window": 1},
    {"consecutive_bars": 1},
    {"volume_ratio_min": 1.0},
    {"shrink_max": 1.5},
    {"stagnant_pct": -1.0},
    {"stagnant_max_drawdown_pct": -1.0},
    {"low_position_pct": 100.0},
])
def test_invalid_params_raise_value_error(params):
    """非法参数必须是 ValueError，接口据此回 invalid_parameters。"""
    with pytest.raises(ValueError):
        compute(make_bars([10.0] * 30, [100.0] * 30), **params)
