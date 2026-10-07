"""MACD 与 KDJ 的预热期语义。

两者原来的问题都属于"把算不出来伪装成算出来了"：
- MACD：`_ema` 用首值播种且不返回 None，于是第 0 根的 DIF/DEA/柱体全是 0，
  advisor 的"柱体转正"规则在预热期就是靠这个 0 在判信号。
- KDJ：`m1`/`m2` 读了没用（平滑系数写死 2/3、1/3），且第 n-1 根明明能算出 RSV
  却被填成种子 50。
"""

from app.engine.indicator.base import _ema, _rma, _sma
from app.engine.indicator.kdj import KDJCalculator
from app.engine.indicator.macd import MACDCalculator


def make_klines(count: int) -> list[dict]:
    rows = []
    for index in range(count):
        close = 100.0 + index * 0.4 + ((index % 5) - 2) * 0.9
        rows.append({
            "open_time": 1_700_000_000_000 + index * 86_400_000,
            "open": close - 0.3, "high": close + 1.2, "low": close - 1.1,
            "close": close, "volume": 1000 + (index % 7) * 100,
        })
    return rows


def test_ema_and_rma_share_the_sma_seed_and_none_warmup():
    values = [float(index) for index in range(30)]

    ema = _ema(values, 14)
    rma = _rma(values, 14)
    sma = _sma(values, 14)

    assert all(value is None for value in ema[:13])
    assert all(value is None for value in rma[:13])
    # 播种点三者相同（都是前 14 个值的均值）
    assert ema[13] == rma[13] == sma[13]
    # 之后 RMA(alpha=1/n) 与 EMA(alpha=2/(n+1)) 必须分道扬镳
    assert ema[20] != rma[20], "RMA 与 EMA 的平滑系数不同，不能互相替代"


def test_ema_accepts_leading_none_for_chained_averages():
    """DEA 是 DIF 的均线，上游有一段 None——播种窗口内残缺时应整段留 None。"""
    values: list[float | None] = [None] * 5 + [float(index) for index in range(25)]

    result = _ema(values, 9)

    assert all(value is None for value in result[:13])
    assert result[13] is not None


def test_macd_warmup_is_none_instead_of_zero():
    klines = make_klines(60)
    result = MACDCalculator().calculate(klines, {})

    assert len(result.values) == len(klines)
    # DIF 从第 slow-1 = 25 根起有效
    assert all(row["dif"] is None for row in result.values[:25])
    assert result.values[25]["dif"] is not None
    # DEA 是 DIF 的均线，再多 signal-1 = 8 根 → 第 33 根
    assert all(row["dea"] is None for row in result.values[:33])
    assert result.values[33]["dea"] is not None
    # 预热期的柱体不能是 0（那会被"柱体转正"当成信号）
    assert all(row["histogram"] is None for row in result.values[:33])


def test_macd_rejects_inverted_periods():
    klines = make_klines(60)
    for params in ({"fast": 26, "slow": 12}, {"fast": 0}, {"signal": 0}):
        try:
            MACDCalculator().calculate(klines, params)
        except ValueError:
            continue
        raise AssertionError(f"参数 {params} 应当被拒绝")


def test_kdj_uses_m1_and_m2():
    """修复前 m1=3/m2=3 与 m1=5/m2=8 输出完全一致（参数是死的）。"""
    klines = make_klines(60)
    default = KDJCalculator().calculate(klines, {"n": 9, "m1": 3, "m2": 3})
    smoothed = KDJCalculator().calculate(klines, {"n": 9, "m1": 5, "m2": 8})

    assert default.values[-1]["k"] != smoothed.values[-1]["k"]
    assert default.values[-1]["d"] != smoothed.values[-1]["d"]
    # m1=m2=3 时必须与经典口径 (2/3, 1/3) 等价
    assert abs(default.values[-1]["j"] - (3 * default.values[-1]["k"] - 2 * default.values[-1]["d"])) < 1e-3


def test_kdj_first_value_lands_on_the_first_computable_bar():
    klines = make_klines(30)
    result = KDJCalculator().calculate(klines, {"n": 9, "m1": 3, "m2": 3})

    assert len(result.values) == len(klines)
    # n=9 → 第 8 根就有完整的 9 根窗口，RSV 可算
    assert all(row["k"] is None for row in result.values[:8]), "预热期必须是 None"
    assert result.values[8]["k"] is not None, "第 8 根就能算 RSV，不该还是种子 50"


def test_kdj_rejects_invalid_params():
    klines = make_klines(30)
    for params in ({"n": 1}, {"m1": 0}, {"m2": -1}):
        try:
            KDJCalculator().calculate(klines, params)
        except ValueError:
            continue
        raise AssertionError(f"参数 {params} 应当被拒绝")
