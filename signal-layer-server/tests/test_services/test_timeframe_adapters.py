from app.adapters.akshare_adapter import TF_MINUTE as AKSHARE_MINUTE
from app.adapters.baostock_adapter import TF_FREQ as BAOSTOCK_FREQ
from app.adapters.binance_adapter import TF_MAP as MYSQL_TIMEFRAME
from app.adapters.futures_adapter import TF_MINUTE as FUTURES_MINUTE


def test_all_market_adapters_map_five_minute_timeframe():
    assert MYSQL_TIMEFRAME["5m"] == "5分钟"
    assert AKSHARE_MINUTE["5m"] == "5"
    assert BAOSTOCK_FREQ["5m"] == "5"
    assert FUTURES_MINUTE["5m"] == "5"
