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


def test_ma_omits_values_during_warmup():
    """样本不足 period 根时不出值：不能拿收盘价顶替，否则会画出一条假均线。"""
    bars = [bar(i, 10.0 + i, 10.2 + i, 9.8 + i, 10.0 + i) for i in range(5)]

    result = MACalculator().calculate(bars, {"period": 3})

    # 前 period-1 根（0、1）无值
    assert result.values[0]["value"] is None
    assert result.values[1]["value"] is None
    assert result.values[0]["support"] == 0
    assert result.values[0]["resistance"] == 0

    # 第 period-1 根起为真实均值，且不等于收盘价
    assert result.values[2]["value"] == (10.0 + 11.0 + 12.0) / 3
    assert result.values[3]["value"] == (11.0 + 12.0 + 13.0) / 3


def test_ma_with_insufficient_history_yields_no_values_at_all():
    """历史长度不足一个周期时，整条序列都不该有值。"""
    bars = [bar(i, 10.0 + i, 10.2 + i, 9.8 + i, 10.0 + i) for i in range(4)]

    result = MACalculator().calculate(bars, {"period": 10})

    assert all(item["value"] is None for item in result.values)
    assert all(item["support"] == 0 and item["resistance"] == 0 for item in result.values)

