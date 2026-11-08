"""MACD 柱群背驰的口径与信号落点。

口径：相邻两个红柱群（绿柱群）里，前群面积更大、价格却创新高（新低），
就是顶背驰（底背驰）；信号落在后一群收完的下一根，箭头连接两群的峰位。
"""

from app.api.indicator import INDICATOR_META
from app.engine.indicator.macd import MACDCalculator
from app.engine.indicator.macd_divergence import detect_macd_divergences


def _hist(parts: list[tuple[float, int]]) -> list[float]:
    values: list[float] = []
    for value, count in parts:
        values.extend([value] * count)
    return values


# 红群（0-2）面积 1.2、峰在 1；绿群（3-4）；红群（5-7）面积 0.55、峰在 6；
# 第 8 根转绿 = 后群收完的确认根。
TOP_HIST = [0.4, 0.5, 0.3, -0.2, -0.15, 0.2, 0.25, 0.1, -0.1]
TOP_HIGHS = [108, 110, 109, 105, 104, 111, 112, 110, 110]
TOP_LOWS = [106, 108, 107, 103, 102, 109, 110, 108, 108]

# 对称的底背驰：绿群面积变小、价格创新低，确认根在第 8 根。
BOTTOM_HIST = [-0.4, -0.5, -0.3, 0.2, 0.15, -0.2, -0.25, -0.1, 0.1]
BOTTOM_HIGHS = [112, 114, 113, 116, 117, 113, 111, 112, 115]
BOTTOM_LOWS = [110, 112, 111, 114, 115, 111, 109, 110, 113]


def test_top_divergence_needs_smaller_second_group_and_new_high():
    found = detect_macd_divergences(TOP_HIST, TOP_HIGHS, TOP_LOWS)

    assert len(found) == 1
    item = found[0]
    assert item.kind == "top"
    assert item.confirm_index == 8
    assert (item.from_index, item.from_value) == (1, 0.5)
    assert (item.to_index, item.to_value) == (6, 0.25)
    assert item.reference_area > item.current_area
    assert item.strength_ratio < 1


def test_bottom_divergence_is_the_mirror_case():
    found = detect_macd_divergences(BOTTOM_HIST, BOTTOM_HIGHS, BOTTOM_LOWS)

    assert len(found) == 1
    assert found[0].kind == "bottom"
    assert found[0].confirm_index == 8
    assert found[0].to_value == -0.25


def test_no_signal_when_second_group_is_not_smaller():
    larger = list(TOP_HIST)
    larger[6] = 1.0  # 后群面积 0.2 + 1.0 + 0.1 = 1.3 > 前群 1.2
    assert detect_macd_divergences(larger, TOP_HIGHS, TOP_LOWS) == []


def test_no_signal_without_new_high():
    flat = list(TOP_HIGHS)
    flat[5:8] = [108, 109, 109]  # 后群最高价 109，没有超过前群的 110
    assert detect_macd_divergences(TOP_HIST, flat, TOP_LOWS) == []


def test_signal_waits_for_the_second_group_to_close():
    # 砍掉确认根：后群还没收完，面积还会变，不能出信号
    assert detect_macd_divergences(TOP_HIST[:8], TOP_HIGHS[:8], TOP_LOWS[:8]) == []


def test_min_bars_filters_short_groups():
    short_second = [0.4, 0.5, 0.3, -0.2, -0.15, 0.2, 0.25, -0.1]
    highs = TOP_HIGHS[:8]
    lows = TOP_LOWS[:8]
    assert detect_macd_divergences(short_second, highs, lows, min_bars=3) == []
    assert len(detect_macd_divergences(short_second, highs, lows, min_bars=2)) == 1


def test_invalid_min_bars_is_rejected():
    for bad in (0, -2):
        try:
            detect_macd_divergences(TOP_HIST, TOP_HIGHS, TOP_LOWS, min_bars=bad)
        except ValueError:
            continue
        raise AssertionError(f"min_bars={bad} 应当被拒绝")


def make_klines(closes: list[float]) -> list[dict]:
    return [
        {
            "open_time": 1_700_000_000_000 + index * 86_400_000,
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1000,
        }
        for index, close in enumerate(closes)
    ]


def make_divergence_klines() -> list[dict]:
    """横盘预热 → 强涨 → 回调 → 更弱的上涨但创新高 → 回落。"""
    closes: list[float] = [100.0] * 40                            # 预热，DIF/DEA 收敛
    closes += [100 + index * 1.5 for index in range(1, 21)]       # 101.5 → 130
    closes += [130 - index * 0.8 for index in range(1, 11)]       # 129.2 → 122
    closes += [122 + index * 0.6 for index in range(1, 21)]       # 122.6 → 134
    closes += [134 - index * 1.0 for index in range(1, 7)]        # 133 → 128
    return make_klines(closes)


def test_calculator_emits_event_on_confirm_bar_with_matching_arrow():
    result = MACDCalculator().calculate(make_divergence_klines(), {})

    top_count = sum(1 for row in result.values if row["top_divergence"] == 1.0)
    assert top_count > 0, "这段走势应当产生顶背驰"

    by_time = {row["time"]: row for row in result.values}
    for index, row in enumerate(result.values):
        if row["top_divergence"] != 1.0:
            continue
        # 事件落在后群收完的下一根：前一根还是红柱，当根已经转绿
        assert result.values[index - 1]["histogram"] > 0
        assert row["histogram"] <= 0
        assert row["bottom_divergence"] == 0.0

    top_arrows = [item for item in result.render.arrows if item.direction == "top"]
    assert len(top_arrows) == top_count
    for arrow in top_arrows:
        assert arrow.from_time < arrow.to_time
        # 箭头端点必须落在真实柱体的峰位上
        assert by_time[float(arrow.from_time)]["histogram"] == arrow.from_value
        assert by_time[float(arrow.to_time)]["histogram"] == arrow.to_value


def test_histogram_is_red_above_zero_and_green_below():
    result = MACDCalculator().calculate(make_klines([100 + (index % 7) for index in range(80)]), {})

    plot = next(item for item in result.render.plots if item.field == "histogram")
    assert plot.color == "#ff5b62"
    assert plot.negative_color == "#2fc58d"


def test_meta_exposes_both_divergence_filters():
    meta = INDICATOR_META["macd"]

    fields = {item["field"]: item for item in meta["outputs"]}
    assert fields["top_divergence"]["kind"] == "event"
    assert fields["bottom_divergence"]["kind"] == "event"
    assert meta["default_params"]["divergence_min_bars"] == 3
