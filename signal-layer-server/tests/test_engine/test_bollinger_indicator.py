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


def test_bandwidth_is_the_band_span_over_the_middle():
    """带宽（价格单位）与带宽%（相对中轨）是两个字段，关系必须自洽。

    带宽＝上轨−下轨（用户口径，便于与价格/ATR 直接比）；
    带宽%＝带宽/中轨×100（便于跨标的比较与设阈值）。
    """
    rows = [
        {"open_time": index, "open": 10.0, "high": 11.0, "low": 9.0,
         "close": 10.0 + (index % 5) * 0.1, "volume": 100}
        for index in range(30)
    ]
    result = BollingerCalculator().calculate(rows, {"period": 20, "std": 2})

    last = result.values[-1]
    assert abs(last["bandwidth"] - (last["upper"] - last["lower"])) < 1e-6
    # 容差放宽到 1e-4：三个字段各自按不同精度取整（带宽 6 位、轨道 8 位），
    # 反推会有 1e-5 量级的差，这是报文取整而不是公式不一致
    assert abs(last["bandwidth_pct"] - last["bandwidth"] / last["middle"] * 100) < 1e-4


def test_bandwidth_is_none_during_warmup():
    rows = [
        {"open_time": index, "open": 10.0, "high": 11.0, "low": 9.0,
         "close": 10.0 + index * 0.01, "volume": 100}
        for index in range(30)
    ]
    result = BollingerCalculator().calculate(rows, {"period": 20})

    assert all(row["bandwidth"] is None for row in result.values[:19])
    assert result.values[19]["bandwidth"] is not None


def test_bandwidth_series_detects_opening_and_closing():
    """带宽序列要能判出开口与收口——不然「向上/向下」这两个操作符就没意义。

    造"宽幅 → 窄幅 → 宽幅"三段行情：带宽应当先收窄（收口）再走阔（开口），
    两个方向都必须出现。
    """
    rows = []
    for index in range(120):
        amplitude = 0.2 if 40 <= index < 80 else 1.5
        close = 10.0 + (amplitude if index % 2 == 0 else -amplitude)
        rows.append({
            "open_time": index, "open": close, "high": close + amplitude,
            "low": close - amplitude, "close": close, "volume": 100,
        })
    result = BollingerCalculator().calculate(rows, {"period": 20})

    values = [row["bandwidth"] for row in result.values if row["bandwidth"] is not None]
    assert len(values) > 40
    falling = [a for a, b in zip(values, values[1:]) if b < a]
    rising = [a for a, b in zip(values, values[1:]) if b > a]
    assert rising and falling, f"应有开口与收口两个方向，实际 rising={len(rising)} falling={len(falling)}"
    # 窄幅段的带宽必须显著低于两侧宽幅段
    assert min(values[len(values) // 2 - 5:len(values) // 2 + 5]) < max(values[:10])


def _amplitude_rows(count: int, widths: list[float]) -> list[dict]:
    """按给定振幅分段构造行情（振幅决定带宽大小）。"""
    rows = []
    for index in range(count):
        amplitude = widths[min(index * len(widths) // count, len(widths) - 1)]
        close = 10.0 + (amplitude if index % 2 == 0 else -amplitude)
        rows.append({
            "open_time": index, "open": close, "high": close + amplitude,
            "low": close - amplitude, "close": close, "volume": 100,
        })
    return rows


def test_bandwidth_is_the_raw_span():
    """带宽 = 上轨 − 下轨（价格单位），与相对中轨的百分比版本分开。"""
    rows = _amplitude_rows(60, [1.0])
    result = BollingerCalculator().calculate(rows, {"period": 20, "std": 2})

    last = result.values[-1]
    assert abs(last["bandwidth"] - (last["upper"] - last["lower"])) < 1e-6
    # 容差放宽到 1e-4：三个字段各自按不同精度取整（带宽 6 位、轨道 8 位），
    # 反推会有 1e-5 量级的差，这是报文取整而不是公式不一致
    assert abs(last["bandwidth_pct"] - last["bandwidth"] / last["middle"] * 100) < 1e-4


def test_squeeze_fires_only_after_the_band_narrows_beyond_the_threshold():
    """收口＝带宽比若干根之前收窄超过阈值。

    这条测试的重点是"阈值真的在起作用"：不带阈值的收窄几乎每根都成立，
    那当条件用毫无意义。
    """
    # 宽幅 → 窄幅：带宽持续收窄
    rows = _amplitude_rows(120, [1.5, 1.5, 0.2, 0.2])
    result = BollingerCalculator().calculate(
        rows, {"period": 20, "std": 2, "squeeze_lookback": 10, "squeeze_threshold_pct": 10},
    )

    fired = [index for index, row in enumerate(result.values) if row["band_squeeze"] > 0]
    assert fired, "带宽大幅收窄时应报收口"
    # 预热期 + 对比样本不足期不能报
    assert min(fired) >= 20 + 10 - 1, f"前段不该报收口，实际最早在第 {min(fired)} 根"
    # 收口与开口互斥
    assert all(row["band_expand"] == 0 or row["band_squeeze"] == 0 for row in result.values)


def test_expand_fires_on_widening():
    rows = _amplitude_rows(120, [0.2, 0.2, 1.5, 1.5])
    result = BollingerCalculator().calculate(rows, {"period": 20, "std": 2})

    fired = [index for index, row in enumerate(result.values) if row["band_expand"] > 0]
    assert fired, "带宽大幅走阔时应报开口"


def test_small_drift_does_not_fire_without_reaching_the_threshold():
    """带宽缓慢变化、幅度始终低于阈值 → 既不报开口也不报收口。"""
    rows = _amplitude_rows(120, [1.0, 1.005, 1.01, 1.015])
    result = BollingerCalculator().calculate(
        rows, {"period": 20, "std": 2, "squeeze_lookback": 10, "squeeze_threshold_pct": 10},
    )

    assert all(row["band_expand"] == 0.0 for row in result.values), "幅度不足阈值不该报开口"
    assert all(row["band_squeeze"] == 0.0 for row in result.values), "幅度不足阈值不该报收口"


def test_squeeze_events_are_causal():
    """开口/收口只能看历史：截断重算的结果必须逐位一致。"""
    calculator = BollingerCalculator()
    rows = _amplitude_rows(160, [1.5, 1.5, 0.2, 0.2])
    full = calculator.calculate(rows, {"period": 20})
    prefix = calculator.calculate(rows[:120], {"period": 20})

    for index in range(120):
        for field in ("band_squeeze", "band_expand", "bandwidth"):
            assert prefix.values[index][field] == full.values[index][field]


def test_squeeze_params_are_validated():
    rows = _amplitude_rows(60, [1.0])
    for params in ({"squeeze_lookback": 0}, {"squeeze_threshold_pct": 0}, {"squeeze_threshold_pct": 200}):
        try:
            BollingerCalculator().calculate(rows, params)
        except ValueError:
            continue
        raise AssertionError(f"参数 {params} 应被拒绝")
