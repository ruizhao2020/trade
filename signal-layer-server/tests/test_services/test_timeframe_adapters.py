from app.adapters.akshare_adapter import TF_MINUTE as AKSHARE_MINUTE
from app.adapters.akshare_adapter import _row_to_bar
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
