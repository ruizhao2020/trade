"""K 线重叠级别的口径测试。"""

from app.engine.chan.overlap import SUB_LEVEL_MIN_BARS, detect_kline_overlaps


def bars(prices: list[tuple[float, float]], day_start: int = 1_700_000_000_000) -> list[dict]:
    return [
        {"open_time": day_start + index * 86_400_000, "low": low, "high": high}
        for index, (low, high) in enumerate(prices)
    ]


def test_twenty_flat_bars_form_a_sub_level_overlap():
    """20 根 K 线共享一段价格区间 → 次级别重叠段。"""
    rows = bars([(10.0, 11.0)] * 20)

    found = detect_kline_overlaps(rows)

    assert len(found) == 1
    segment = found[0]
    assert segment.bars == 20
    assert segment.level == "sub1"
    assert (segment.low, segment.high) == (10.0, 11.0)
    assert segment.start_index == 0 and segment.end_index == 19


def test_trending_bars_share_no_overlap_and_are_skipped():
    """单边上涨时每根 K 线都不与前一根重叠，短段被过滤掉。"""
    rows = bars([(10.0 + index, 10.5 + index) for index in range(10)])

    assert detect_kline_overlaps(rows) == []


def test_overlap_interval_shrinks_to_the_common_part():
    """公共区间取所有 K 线的交集：下沿取最高 low，上沿取最低 high。"""
    rows = bars([(10.0, 15.0), (11.0, 14.0), (12.0, 13.5)])
    # 再接一根不重叠的 K 线，确保这段在这里结束
    rows.append({"open_time": rows[-1]["open_time"] + 86_400_000, "low": 20.0, "high": 21.0})

    found = detect_kline_overlaps(rows)

    assert len(found) == 1
    assert found[0].bars == 3
    assert (found[0].low, found[0].high) == (12.0, 13.5)


def test_level_bands_follow_bar_counts():
    """按根数分档：18+ 次级别、5-17 次次级别、3-4 过渡区。"""
    assert SUB_LEVEL_MIN_BARS == {"sub1": 18, "sub2": 5, "sub3": 3}

    for count, level in ((18, "sub1"), (17, "sub2"), (5, "sub2"), (4, "sub3"), (3, "sub3")):
        rows = bars([(10.0, 11.0)] * count)
        found = detect_kline_overlaps(rows)
        assert len(found) == 1, count
        assert found[0].level == level, count


def test_min_bars_filter_drops_short_overlaps():
    rows = bars([(10.0, 11.0)] * 4)

    assert detect_kline_overlaps(rows, min_bars=5) == []


def test_segments_are_split_when_intersection_breaks():
    """交集断开后从下一根重新开始，形成两段独立的区间。"""
    rows = bars([(10.0, 11.0)] * 3) + bars([(20.0, 21.0)] * 3)

    found = detect_kline_overlaps(rows)

    assert len(found) == 2
    assert found[0].bars == 3 and found[1].bars == 3
    assert found[0].high == 11.0 and found[1].low == 20.0


def test_empty_input_is_safe():
    assert detect_kline_overlaps([]) == []
