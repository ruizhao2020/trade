from app.services.backtest_service import _indicator_values_until


def test_backtest_slices_indicator_values_by_timestamp_instead_of_array_position():
    values = [
        {"time": 1000.0, "value": 1.0},
        {"time": 3000.0, "value": 3.0},
        {"time": 5000.0, "value": 5.0},
    ]

    assert _indicator_values_until(values, 2999) == [{"time": 1000.0, "value": 1.0}]
    assert _indicator_values_until(values, 3000)[-1]["value"] == 3.0
