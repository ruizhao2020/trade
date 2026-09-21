from app.engine.indicator.ma import MACalculator


def bar(index: int, open_price: float, high: float, low: float, close: float) -> dict:
    return {
        "open_time": index,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": 100,
    }


def test_ma_detects_support_and_resistance_after_warmup():
    result = MACalculator().calculate([
        bar(1, 10.0, 10.1, 9.9, 10.0),
        bar(2, 10.0, 10.1, 9.9, 10.0),
        bar(3, 9.9, 10.3, 9.8, 10.2),   # 触碰MA后收回上方，阳线
        bar(4, 10.2, 10.3, 9.9, 10.0),  # 触碰MA后收回下方，阴线
    ], {"period": 3, "touch_tolerance_pct": 0.5})

    assert result.values[0]["support"] == 0
    assert result.values[1]["resistance"] == 0
    assert result.values[2]["support"] == 1
    assert result.values[2]["resistance"] == 0
    assert result.values[3]["support"] == 0
    assert result.values[3]["resistance"] == 1
