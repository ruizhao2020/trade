from app.adapters.akshare_adapter import TF_MINUTE as AKSHARE_MINUTE
from datetime import date

from app.adapters.akshare_adapter import _factor_for_date, _row_to_bar
from app.adapters.baostock_adapter import TF_FREQ as BAOSTOCK_FREQ
from app.adapters.binance_adapter import TF_MAP as MYSQL_TIMEFRAME
from app.adapters.futures_adapter import TF_MINUTE as FUTURES_MINUTE


def test_all_market_adapters_map_five_minute_timeframe():
    assert MYSQL_TIMEFRAME["5m"] == "5分钟"
    assert AKSHARE_MINUTE["5m"] == "5"
    assert BAOSTOCK_FREQ["5m"] == "5"
    assert FUTURES_MINUTE["5m"] == "5"


def test_akshare_daily_row_accepts_iso_date_string():
    bar = _row_to_bar({
        "日期": "2026-09-10",
        "开盘": 10.0,
        "最高": 10.8,
        "最低": 9.8,
        "收盘": 10.5,
        "成交量": 12345,
    })
    assert bar["open"] == 10.0
    assert bar["close"] == 10.5
    assert bar["open_time"] > 0


def test_akshare_minute_row_accepts_english_columns():
    bar = _row_to_bar({
        "day": "2026-09-10 09:35:00",
        "open": "10.0",
        "high": "10.8",
        "low": "9.8",
        "close": "10.5",
        "volume": "12345",
        "amount": "129000",
    })
    assert bar["close"] == 10.5
    assert bar["amount"] == 129000


def test_akshare_daily_row_preserves_chip_distribution_fields():
    bar = _row_to_bar({
        "date": date(2026, 9, 10),
        "open": 10,
        "high": 11,
        "low": 9,
        "close": 10.5,
        "volume": 1_000_000,
        "amount": 10_500_000,
        "turnover_rate": 2.5,
        "circulating_shares": 40_000_000,
        "adjustment_factor": 1.12,
        "adjustment_type": "qfq",
    })
    assert bar["turnover_rate"] == 2.5
    assert bar["circulating_shares"] == 40_000_000
    assert bar["adjustment_factor"] == 1.12
    assert bar["adjustment_type"] == "qfq"


def test_qfq_factor_uses_latest_effective_value_for_trade_date():
    events = [(date(2025, 1, 1), 1.2), (date(2026, 6, 1), 1.0)]
    assert _factor_for_date(events, "2026-05-31") == 1.2
    assert _factor_for_date(events, date(2026, 9, 10)) == 1.0
