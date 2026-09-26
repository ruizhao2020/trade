from app.engine.indicator.bollinger import BollingerCalculator


def bar(index: int, close: float) -> dict:
    return {
        "open_time": index,
        "open": close,
        "high": close + 0.2,
        "low": close - 0.2,
        "close": close,
        "volume": 100,
    }


def test_bollinger_omits_bands_during_warmup():
    """布林带同样不能在预热期用收盘价顶替，否则上下轨会与价格重合。"""
    bars = [bar(i, 10.0 + i) for i in range(5)]

    result = BollingerCalculator().calculate(bars, {"period": 3, "std": 2.0})

    for index in (0, 1):
        assert result.values[index]["upper"] is None
        assert result.values[index]["middle"] is None
        assert result.values[index]["lower"] is None

    # 第 period-1 根起为真实中轨
    assert result.values[2]["middle"] == (10.0 + 11.0 + 12.0) / 3
    assert result.values[2]["upper"] > result.values[2]["middle"] > result.values[2]["lower"]


def test_bollinger_with_insufficient_history_yields_no_bands():
    bars = [bar(i, 10.0 + i) for i in range(4)]

    result = BollingerCalculator().calculate(bars, {"period": 10, "std": 2.0})

    assert all(
        item["upper"] is None and item["middle"] is None and item["lower"] is None
        for item in result.values
    )
