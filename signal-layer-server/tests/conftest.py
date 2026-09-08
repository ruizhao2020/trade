import pytest


@pytest.fixture
def sample_klines():
    return [
        {
            "open_time": 1717200000000 + i * 900000,
            "open": 50000.0 + i * 50,
            "high": 50100.0 + i * 50,
            "low": 49900.0 + i * 50,
            "close": 50050.0 + i * 50,
            "volume": 100.0 + i,
            "turnover": 5000000.0,
            "is_closed": True,
        }
        for i in range(200)
    ]
