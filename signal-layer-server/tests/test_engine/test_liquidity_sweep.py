"""流动性扫荡：ATR 口径、预热期静默、参数校验。

这个指标是 Pine 脚本的移植，但此前**一个测试都没有**，于是三处与原版的偏差
（HTF 过滤失效、ATR 用错平滑、na 门槛被架空）全部处于无覆盖状态。
这里补的是"与原版语义一致"的部分：ATR 用 Wilder 平滑、预热期不发信号、
参数越界要报错而不是给出垃圾门限。
"""

import math

import pytest

from app.engine.indicator.liquidity_sweep import LiquiditySweepCalculator


def make_klines(count: int = 240) -> list[dict]:
    rows = []
    price = 100.0
    for index in range(count):
        wave = math.sin(index / 6.0) * 2.2
        close = 100.0 + wave
        rows.append({
            "open_time": 1_700_000_000_000 + index * 3_600_000,
            "open": price,
            "high": max(price, close) + 0.7 + (0.3 if index % 11 == 0 else 0.0),
            "low": min(price, close) - 0.7,
            "close": close,
            "volume": 1000 + (index % 7) * 50,
        })
        price = close
    return rows


def signals(result) -> list[int]:
    return [
        index for index, row in enumerate(result.values)
        if row["bull_signal"] or row["bear_signal"]
    ]


def test_values_align_and_atr_warms_up_as_none():
    klines = make_klines()
    result = LiquiditySweepCalculator().calculate(klines, {"atr_len": 14})

    assert len(result.values) == len(klines)
    # Wilder 平滑：前 atr_len-1 根没有 ATR
    assert all(row["atr"] is None for row in result.values[:13])
    assert result.values[13]["atr"] is not None
    # 不能拿 0 顶上（那会让下面的 na 门槛恒真）
    assert all(row["atr"] != 0.0 for row in result.values[:13])


def test_no_signals_during_atr_warmup():
    """预热期不能发信号：原版的门槛是 `not na(atr)`。

    修复前 `atr_ok = bar_atr > 0` 配合 `_ema` 的播种值恒真，
    于是预热期照常出信号，而参考脚本一根都不出。
    """
    klines = make_klines()
    for atr_len in (14, 30):
        result = LiquiditySweepCalculator().calculate(klines, {"atr_len": atr_len})
        early = [index for index in signals(result) if index < atr_len - 1]
        assert early == [], f"atr_len={atr_len} 时预热期出现了信号：{early}"


def test_signals_are_prefix_causal():
    """信号的前缀不变性：截断重算，前 k 根的信号必须与全量一致。"""
    klines = make_klines()
    full = LiquiditySweepCalculator().calculate(klines, {})
    for length in (150, 200):
        prefix = LiquiditySweepCalculator().calculate(klines[:length], {})
        for index in range(length):
            assert prefix.values[index]["bull_signal"] == full.values[index]["bull_signal"]
            assert prefix.values[index]["bear_signal"] == full.values[index]["bear_signal"]


def test_htf_params_are_gone():
    """HTF 过滤未实现，所以参数也不该再存在。

    曾经这两个参数会被读取、回显并在指标描述里宣称"HTF趋势对齐"，
    使用者会以为过滤在生效。真正接入需要服务层传高周期 K 线。
    """
    result = LiquiditySweepCalculator().calculate(make_klines(), {})

    assert "use_htf" not in result.params
    assert "htf_ema_len" not in result.params


@pytest.mark.parametrize("params", [
    {"piv_len": 0}, {"piv_len": 1}, {"piv_len": 61},
    {"reclaim_win": 0}, {"atr_len": 1}, {"max_levels": 0},
    {"min_wick_atr": 3.0, "max_wick_atr": 1.0}, {"vol_len": 0},
    {"cooldown_bars": -1}, {"dir_mode": "short only"},
])
def test_invalid_params_raise_value_error(params):
    """越界参数必须报错，不能变成 min([]) 崩溃或随机的 ATR 门限。"""
    with pytest.raises(ValueError):
        LiquiditySweepCalculator().calculate(make_klines(), params)
