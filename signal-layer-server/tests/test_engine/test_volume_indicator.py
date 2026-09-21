import pytest

from app.engine.indicator.volume import VolumeCalculator


def kline(timestamp: int, volume: float) -> dict:
    return {
        "open_time": timestamp,
        "open": 10,
        "high": 11,
        "low": 9,
        "close": 10,
        "volume": volume,
    }


def test_volume_indicator_classifies_relative_volume_bars():
    result = VolumeCalculator().calculate([
        kline(1, 100),
        kline(2, 70),    # 0.7，缩量
        kline(3, 100),   # 1.43，增量
        kline(4, 220),   # 2.2，倍量
        kline(5, 700),   # 3.18，三倍量
        kline(6, 3500),  # 5.0，多倍量
    ], {})

    assert [item["volume_class"] for item in result.values] == [0, 1, 2, 3, 4, 5]
    assert result.values[3]["is_double_volume"] == 1
    assert result.values[4]["is_triple_volume"] == 1
    assert result.values[5]["is_multiple_volume"] == 1
    assert all(item["is_up"] == 1 for item in result.values)
    assert result.render.window == "sub"
    assert result.render.plots[0].type == "histogram"


def test_volume_indicator_rejects_overlapping_thresholds():
    with pytest.raises(ValueError, match="成交量阈值"):
        VolumeCalculator().calculate([kline(1, 100)], {"double_min": 1.0})


def test_volume_indicator_detects_shapes_streaks_and_relative_volume():
    result = VolumeCalculator().calculate([
        kline(1, 100),
        kline(2, 110),
        kline(3, 130),   # 连续3根放量，梯量柱，同时为3根高量
        kline(4, 120),
        kline(5, 110),   # 连续3根缩量
        kline(6, 111),   # 平量
        kline(7, 80),    # 3根窗口低量
    ], {"lookback": 3, "sequence_length": 3, "flat_tolerance": 0.02, "relative_period": 3})

    assert result.values[2]["is_high_volume"] == 1
    assert result.values[2]["is_ladder_volume"] == 1
    assert result.values[2]["volume_shape"] == 4
    assert result.values[4]["is_contracting_volume"] == 1
    assert result.values[4]["volume_shape"] == 5
    assert result.values[5]["is_flat_volume"] == 1
    assert result.values[6]["is_low_volume"] == 1
    assert result.values[6]["relative_volume"] > 0
