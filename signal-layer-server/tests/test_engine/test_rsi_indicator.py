"""RSI：输出对齐、bar 标注与 Wilder 平滑。

修复前的实现有两处错位，且都没有测试覆盖：
- `values` 比 klines 短 period 行（第 1..period 根完全没有行）
- 每个值被贴到了后一根上（图上整条线左移一格，条件判断读到的是前一根的 RSI）

这里用一个独立实现的 Wilder RSI 逐根对拍——不用"快照式"断言，
因为快照式只能锁住当前输出，发现不了"整条序列错位一根"这类错误。
"""

from app.engine.indicator.rsi import RSICalculator


def make_klines(count: int) -> list[dict]:
    rows = []
    for index in range(count):
        close = 100.0 + index * 0.7 + (3.0 if index % 3 == 0 else -1.5)
        rows.append({
            "open_time": 1_700_000_000_000 + index * 86_400_000,
            "open": close - 0.5, "high": close + 1.0, "low": close - 1.0,
            "close": close, "volume": 1000 + index,
        })
    return rows


def reference_wilder_rsi(closes: list[float], period: int) -> dict[int, float]:
    """独立实现的 Wilder RSI：返回 {bar 下标: 值}，首值落在第 period 根。"""
    gains = [max(closes[i] - closes[i - 1], 0.0) for i in range(1, len(closes))]
    losses = [max(closes[i - 1] - closes[i], 0.0) for i in range(1, len(closes))]
    average_gain = sum(gains[:period]) / period
    average_loss = sum(losses[:period]) / period

    def rsi(gain: float, loss: float) -> float:
        return 100.0 if loss == 0 else 100.0 - 100.0 / (1.0 + gain / loss)

    values = {period: rsi(average_gain, average_loss)}
    for index in range(period, len(gains)):
        average_gain = (average_gain * (period - 1) + gains[index]) / period
        average_loss = (average_loss * (period - 1) + losses[index]) / period
        values[index + 1] = rsi(average_gain, average_loss)
    return values


def test_rsi_aligns_with_klines_and_matches_reference():
    klines = make_klines(60)
    result = RSICalculator().calculate(klines, {"period": 14})

    assert len(result.values) == len(klines), "必须逐根等长"
    assert [int(row["time"]) for row in result.values] == [row["open_time"] for row in klines]

    reference = reference_wilder_rsi([row["close"] for row in klines], 14)
    for index, row in enumerate(result.values):
        expected = reference.get(index)
        if expected is None:
            assert row["value"] is None, f"第 {index} 根应处于预热期"
            continue
        # 输出保留 4 位小数
        assert abs(row["value"] - expected) < 5e-5, f"第 {index} 根的 RSI 与标准算法不符"


def test_rsi_warmup_is_none_not_a_fake_value():
    result = RSICalculator().calculate(make_klines(30), {"period": 14})

    assert all(row["value"] is None for row in result.values[:14])
    assert result.values[14]["value"] is not None
    # 第一个有效值必须落在第 period 根，不能是种子 50
    assert abs(result.values[14]["value"] - 50.0) > 1e-9


def test_rsi_parameter_changes_the_series():
    klines = make_klines(60)
    fast = RSICalculator().calculate(klines, {"period": 6})
    slow = RSICalculator().calculate(klines, {"period": 14})

    assert fast.values[6]["value"] is not None
    assert slow.values[6]["value"] is None
    assert fast.values[-1]["value"] != slow.values[-1]["value"]


def test_rsi_rejects_invalid_period():
    for period in (0, 1, -5, 500):
        try:
            RSICalculator().calculate(make_klines(30), {"period": period})
        except ValueError:
            continue
        raise AssertionError(f"period={period} 应当被拒绝")
