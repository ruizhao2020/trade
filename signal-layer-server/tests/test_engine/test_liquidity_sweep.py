"""流动性扫荡：ATR 口径、预热期静默、参数校验。

这个指标是 Pine 脚本的移植，但此前**一个测试都没有**，于是三处与原版的偏差
（HTF 过滤失效、ATR 用错平滑、na 门槛被架空）全部处于无覆盖状态。
这里补的是"与原版语义一致"的部分：ATR 用 Wilder 平滑、预热期不发信号、
参数越界要报错而不是给出垃圾门限。
"""

import math

import pytest

from app.api.indicator import INDICATOR_META
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


# ── 展示：信号用标记而不是折线 ──────────────────────────────────────────

def test_signals_are_rendered_as_markers_on_the_swept_level():
    """信号必须走 markers，并挂在被扫的那个价位上。

    原来这里是两条 `line` plot，字段值是 0/1——把"事件标记"当成连续序列画进主图。
    前端给主图叠加线用的是默认价格轴，于是价格轴要容纳 -1 和报价两端，K 线被压扁。
    改成 marker 后既不参与价格轴缩放，又能标出"扫荡发生在哪个价位"。
    """
    result = LiquiditySweepCalculator().calculate(make_klines(), {})

    assert result.render.window == "main"
    assert result.render.plots == [], "信号不该再以折线形式叠加到主图"
    fields = [marker.field for marker in result.render.markers]
    assert fields == ["bull_signal", "bear_signal"]
    # 标记要挂在被扫的价位上，而不是固定在 K 线上下方
    by_field = {marker.field: marker for marker in result.render.markers}
    assert by_field["bull_signal"].price_field == "bull_level"
    assert by_field["bear_signal"].price_field == "bear_level"
    assert by_field["bull_signal"].buy_label == "SSL SWEEP"
    assert by_field["bear_signal"].sell_label == "BSL SWEEP"


def test_marker_price_fields_actually_hold_prices():
    """price_field 必须真的能取到价格，否则标记会掉回 K 线上下方。"""
    rows = make_klines()
    result = LiquiditySweepCalculator().calculate(rows, {})
    closes = [row["close"] for row in rows]
    low, high = min(closes), max(closes)

    marked = 0
    for row in result.values:
        for field in ("bull_level", "bear_level"):
            value = row[field]
            if value:
                assert low * 0.9 <= value <= high * 1.1, f"{field}={value} 不像真实价位"
                marked += 1
    assert marked > 0, "样本里应当出现过扫荡信号，否则这条测试没意义"


def test_signal_fields_are_exposed_as_decision_outputs():
    """显式声明 outputs：不声明的话条件编辑器会回退到 render.plots，
    而信号现在走 markers、plots 为空 → 界面上一个可选字段都没有。"""
    outputs = {item["field"] for item in INDICATOR_META["liquidity_sweep"]["outputs"]}
    assert {"bull_signal", "bear_signal", "bull_level", "bear_level", "atr"} <= outputs


def test_description_says_the_trade_model_is_out_of_scope():
    """参考脚本的 SL/TP 线默认是开的，迁移过来的用户会预期看到——
    描述里必须说明本指标不含交易模型，避免预期错位。"""
    description = INDICATOR_META["liquidity_sweep"]["description"]
    assert "交易模型" in description


def test_marker_colours_follow_the_apps_up_down_convention():
    """看涨用红族、看跌用绿族——与本应用 K 线/量柱的涨跌配色一致。

    参考脚本用的是西方约定（青＝涨、品红＝跌），照搬会让这张图上的颜色
    与页面其它地方的涨跌含义正好相反，因此这里刻意与原版不同。
    前端图例与释义图的颜色由接口的 render.markers 带出，改这里三处一起变。
    """
    import app.engine.indicator.liquidity_sweep as module

    result = LiquiditySweepCalculator().calculate(make_klines(), {})
    bull = next(marker for marker in result.render.markers if marker.field == "bull_signal")
    bear = next(marker for marker in result.render.markers if marker.field == "bear_signal")

    assert bull.buy_color == module.BULL_COLOR
    assert bear.sell_color == module.BEAR_COLOR
    # 红涨绿跌：看涨不该是绿族，看跌不该是红族
    assert module.BULL_COLOR != "#00E5C0", "看涨不能用原版的青色（那是西方约定的跌色）"
    assert module.BEAR_COLOR != "#FF2E93"
