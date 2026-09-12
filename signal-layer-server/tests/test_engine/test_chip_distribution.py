from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone

from app.engine.indicator.chip_distribution import ChipDistributionCalculator


def bar(index: int, close: float, turnover_rate: float | None = 5.0) -> dict:
    return {
        "open_time": index,
        "open": close - 0.1,
        "high": close + 0.5,
        "low": close - 0.5,
        "close": close,
        "volume": 1_000_000,
        "amount": close * 1_000_000,
        "turnover_rate": turnover_rate,
        "circulating_shares": 20_000_000,
        "adjustment_factor": 1.0,
        "adjustment_type": "qfq",
    }


def test_chip_distribution_produces_normalized_profile_and_metrics():
    rows = [bar(index, 10 + index * 0.05) for index in range(60)]
    result = ChipDistributionCalculator().calculate(rows, {"bins": 80, "lookback": 60})

    assert len(result.values) == 80
    assert sum(item["weight"] for item in result.values) == pytest.approx(100, abs=1e-5)
    assert result.render.plots[0].type == "profile"
    metrics = result.values[-1]
    assert 0 <= metrics["profit_ratio"] <= 100
    assert metrics["range70_low"] <= metrics["average_cost"] <= metrics["range70_high"]
    assert metrics["range90_low"] <= metrics["range70_low"]
    assert metrics["range90_high"] >= metrics["range70_high"]
    assert metrics["coverage_ratio"] == 100
    assert result.profile_data is not None
    assert len(result.profile_data.snapshots) == 60
    assert result.profile_data.snapshots[0].time == 0


def test_chip_distribution_can_derive_turnover_from_volume_and_float_shares():
    rows = [bar(index, 10 + index * 0.01, turnover_rate=None) for index in range(30)]
    result = ChipDistributionCalculator().calculate(rows, {"lookback": 30})
    assert result.values[-1]["valid_turnover_days"] == 30


def test_chip_distribution_refuses_incomplete_data_instead_of_guessing():
    rows = [
        {**bar(index, 10, turnover_rate=None), "circulating_shares": None}
        for index in range(30)
    ]
    with pytest.raises(ValueError, match="换手率或流通股本"):
        ChipDistributionCalculator().calculate(rows, {"lookback": 30})


def test_intraday_chip_distribution_starts_from_daily_baseline_and_snapshots_each_bar():
    cn_tz = timezone(timedelta(hours=8))
    start = datetime(2026, 1, 1, tzinfo=cn_tz)
    daily = []
    for index in range(40):
        item = bar(int((start + timedelta(days=index)).timestamp() * 1000), 10 + index * 0.02)
        item["adjustment_factor"] = 1.0
        daily.append(item)
    intraday_day = start + timedelta(days=41)
    intraday = [
        {
            "open_time": int((intraday_day + timedelta(minutes=5 * index)).timestamp() * 1000),
            "open": 10.8 + index * 0.01,
            "high": 10.9 + index * 0.01,
            "low": 10.7 + index * 0.01,
            "close": 10.85 + index * 0.01,
            "volume": 100_000,
            "amount": (10.85 + index * 0.01) * 100_000,
        }
        for index in range(4)
    ]

    result = ChipDistributionCalculator().calculate_with_context(
        intraday,
        {"lookback": 40, "bins": 60},
        {"daily_klines": daily},
    )

    assert result.profile_data is not None
    assert [item.time for item in result.profile_data.snapshots] == [item["open_time"] for item in intraday]
    assert result.profile_data.snapshots[-1].metrics["intraday_bars"] == 4
    assert result.profile_data.snapshots[-1].weights != result.profile_data.snapshots[0].weights
