from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone

from app.engine.indicator.base import ProfileSnapshot
from app.engine.indicator.chip_distribution import ChipDistributionCalculator, _enrich_snapshot_metrics


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

    assert len(result.values) == 60
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
    assert sum(result.profile_data.snapshots[-1].weights) == pytest.approx(100, abs=1e-5)
    assert metrics["time"] == rows[-1]["open_time"]
    assert 0 <= metrics["dominant_peak_ratio"] <= 100
    assert metrics["peak_count"] >= 1
    assert 0 <= metrics["support_chip_ratio"] <= 100
    assert 0 <= metrics["pressure_chip_ratio"] <= 100


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


def test_chip_distribution_coverage_counts_initial_missing_turnover_days():
    rows = [bar(index, 10 + index * 0.01, turnover_rate=None if index < 10 else 5.0) for index in range(30)]
    for item in rows[:10]:
        item["circulating_shares"] = None
    result = ChipDistributionCalculator().calculate(rows, {"lookback": 30, "min_turnover_days": 20})

    assert result.values[-1]["coverage_ratio"] == pytest.approx(66.66666667)


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
    assert len(result.values) == len(intraday)


def test_chip_strategy_events_are_emitted_on_the_current_snapshot_only():
    base = {
        "average_cost": 10.0, "range70_low": 9.5, "range70_high": 10.5,
        "range90_low": 9.0, "range90_high": 11.0, "profit_ratio": 40.0,
        "concentration70": 5.0, "pressure_chip_ratio": 30.0,
        "support_chip_ratio": 20.0, "single_peak": 0.0, "double_peak": 1.0,
    }
    snapshots = [
        ProfileSnapshot(time=1, weights=[100], metrics={**base, "current_price": 9.8, "peak_price": 10.0}),
        ProfileSnapshot(time=2, weights=[100], metrics={**base, "current_price": 10.2, "peak_price": 10.0, "single_peak": 1.0, "double_peak": 0.0}),
    ]
    _enrich_snapshot_metrics(snapshots, {
        "trend_period": 1,
        "migration_threshold_pct": 1.0,
        "concentration_change_threshold": 0.5,
        "pressure_release_threshold": 5.0,
        "retest_tolerance_pct": 1.0,
    })

    assert snapshots[0].metrics["cross_peak_up"] == 0
    assert snapshots[1].metrics["cross_peak_up"] == 1
    assert snapshots[1].metrics["cross_average_cost_up"] == 1
    assert snapshots[1].metrics["single_peak_formed"] == 1
