from app.market_data.ranges import TimeRange, infer_coverage, merge_ranges, missing_ranges


def test_missing_ranges_only_returns_uncovered_middle_segment():
    requested = TimeRange(5, 8)
    covered = [TimeRange(3, 5), TimeRange(7, 8)]
    assert missing_ranges(requested, covered) == [TimeRange(6, 6)]


def test_adjacent_coverage_ranges_are_merged():
    assert merge_ranges([TimeRange(3, 5), TimeRange(6, 8)]) == [TimeRange(3, 8)]


def test_existing_daily_rows_keep_a_large_historical_gap_visible():
    day = 24 * 60 * 60 * 1000
    timestamps = [3 * day, 4 * day, 5 * day, 30 * day, 31 * day]
    assert infer_coverage(timestamps, "1d") == [
        TimeRange(3 * day, 5 * day),
        TimeRange(30 * day, 31 * day),
    ]
