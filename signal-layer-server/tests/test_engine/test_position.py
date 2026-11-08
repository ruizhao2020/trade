"""位置指标的判定口径。"""

from app.engine.indicator.position import PositionCalculator


def make_klines(closes: list[float]) -> list[dict]:
    return [
        {
            "open_time": 1_700_000_000_000 + index * 86_400_000,
            "open": close, "high": close, "low": close, "close": close, "volume": 1000,
        }
        for index, close in enumerate(closes)
    ]


def test_rising_market_is_at_the_top_of_the_range():
    closes = [100.0 + index for index in range(60)]

    result = PositionCalculator().calculate(make_klines(closes), {})

    last = result.values[-1]
    assert last["position_pct"] == 100.0
    assert last["drawdown_pct"] == 0.0


def test_falling_market_is_at_the_bottom_with_drawdown():
    closes = [200.0 - index for index in range(60)]

    result = PositionCalculator().calculate(make_klines(closes), {})

    last = result.values[-1]
    assert last["position_pct"] == 0.0
    assert last["drawdown_pct"] > 0


def test_middle_price_is_around_fifty_percent():
    closes = [100.0] * 30 + [100.0 + index for index in range(1, 30)] + [128.0] * 1
    # 区间 100~128，最后一根在 128 → 100；换成 114 验证中间位置
    closes[-1] = 114.0

    result = PositionCalculator().calculate(make_klines(closes), {})

    last = result.values[-1]
    assert 45 <= last["position_pct"] <= 55


def test_window_param_limits_the_lookback():
    # 前 100 根在 50 附近，随后 20 根涨到 69，最后一根回落到 60
    closes = [50.0 + (index % 3) for index in range(100)] + [50.0 + index for index in range(20)] + [60.0]

    short_window = PositionCalculator().calculate(make_klines(closes), {"window": 20})
    long_window = PositionCalculator().calculate(make_klines(closes), {"window": 500})

    # 20 根窗口：区间 51~69，收 60 → 约 50%
    assert 40 <= short_window.values[-1]["position_pct"] <= 60
    # 500 根窗口：区间 50~69，收 60 → 约 53%
    assert 45 <= long_window.values[-1]["position_pct"] <= 60
    assert short_window.params["window"] == 20
    assert long_window.params["window"] == 500


def test_invalid_window_is_rejected():
    for bad in ({"window": 10}, {"window": 501}):
        try:
            PositionCalculator().calculate(make_klines([100.0] * 60), bad)
        except ValueError:
            continue
        raise AssertionError(f"{bad} 应当被拒绝")


def test_output_is_aligned_and_causal():
    closes = [100.0 + (index % 7) for index in range(120)]

    full = PositionCalculator().calculate(make_klines(closes), {})
    prefix = PositionCalculator().calculate(make_klines(closes[:80]), {})

    assert len(full.values) == 120
    assert prefix.values == full.values[:80]
