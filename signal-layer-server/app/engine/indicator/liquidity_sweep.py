from __future__ import annotations

"""
════════════════════════════════════════════════════════════════════════
Liquidity Sweep Reversal [JOAT] — Python Signal Layer Port
════════════════════════════════════════════════════════════════════════

Port of the Pine Script "Liquidity Sweep Reversal [JOAT]" indicator.
Core signal detection only (Phase 1): swing pivot detection, sweep+reclaim
state machine, and multi-filter final signal gating.

Skipped (Phase 2+):
  - Trade model (entry/SL/TP tracking, R-multiple stats)
  - Dashboard table / VWAP overlay / candle coloring
  - Line/box/label drawing objects
  - HTF cross-timeframe lookup

HTF 趋势对齐尚未实现：原版用 60 分钟 EMA50 过滤多空，本指标只拿到单一周期的
K 线，无法自己取更高周期数据。原先保留了 use_htf / htf_ema_len 两个"读了不用"的
参数，并对外描述成"HTF趋势对齐"——使用者会以为过滤在生效。现已删除这两个参数；
真正接入需要服务层把高周期 K 线通过 context 传进来，属于 Phase 2 的工作。

与原版有意为之的差异：use_vol 开启且成交量均线不可用时，本实现**拒绝**信号
（原版放行）。保守方向更安全，但会让无成交量字段的品种整体不出信号。
"""

DIR_MODES = ("Both", "Long Only", "Short Only")

# 涨跌配色：跟随本应用的约定（红涨绿跌）。
# 前端图例与释义图直接取这两个值（由接口的 render.markers 带出），
# 因此图上标记、图例、图示三处颜色只有一个来源。
BULL_COLOR = "#FF2E93"   # 看涨（SSL SWEEP）
BEAR_COLOR = "#00E5C0"   # 看跌（BSL SWEEP）

from app.engine.indicator.base import (
    IndicatorCalculator, IndicatorResult, MarkerSpec, RenderSpec,
    _get_closes, _get_highs, _get_lows, _get_times, _atr, _param_float, _param_int, _sma,
    register_indicator,
)
from typing import Any


@register_indicator
class LiquiditySweepCalculator(IndicatorCalculator):
    """Liquidity sweep + reclaim reversal signal detector."""

    @property
    def type(self) -> str:
        return "liquidity_sweep"

    def calculate(self, klines: list[dict], params: dict[str, Any]) -> IndicatorResult:
        # ── 01 · ENGINE Params ──────────────────────────────────────────
        piv_len = _param_int(params, "piv_len", 8)
        reclaim_win = _param_int(params, "reclaim_win", 1)
        atr_len = _param_int(params, "atr_len", 14)
        max_levels = _param_int(params, "max_levels", 12)
        max_level_age = _param_int(params, "max_level_age", 600)
        dir_mode = str(params.get("dir_mode", "Both"))  # "Both" | "Long Only" | "Short Only"

        # ── 02 · FILTER Params ──────────────────────────────────────────
        min_wick_atr = _param_float(params, "min_wick_atr", 0.15)
        max_wick_atr = _param_float(params, "max_wick_atr", 2.5)
        use_vol = bool(params.get("use_vol", False))
        vol_len = _param_int(params, "vol_len", 20)
        vol_mult = _param_float(params, "vol_mult", 1.5)
        block_dual = bool(params.get("block_dual", True))
        cooldown_bars = _param_int(params, "cooldown_bars", 3)

        # 参数校验：原版 Pine 有 minval/maxval，缺了会让 piv_len=0 直接
        # 在 min([]) 上抛异常、或让门限变成无意义的数值。
        if not 2 <= piv_len <= 60:
            raise ValueError("摆动点窗口 piv_len 应在 2 到 60 之间")
        if not 1 <= reclaim_win <= 100:
            raise ValueError("回收窗口 reclaim_win 应在 1 到 100 之间")
        if not 2 <= atr_len <= 200:
            raise ValueError("ATR 周期应在 2 到 200 之间")
        if not 1 <= max_levels <= 100:
            raise ValueError("保留的流动性水平数应在 1 到 100 之间")
        if not 10 <= max_level_age <= 10000:
            raise ValueError("流动性水平最长存活根数应在 10 到 10000 之间")
        if not 0 <= min_wick_atr <= 100 or not 0 < max_wick_atr <= 100:
            raise ValueError("影线过滤倍数应在 0 到 100 之间，且上限必须大于 0")
        if min_wick_atr >= max_wick_atr:
            raise ValueError("影线下限必须小于上限")
        if not 1 <= vol_len <= 500:
            raise ValueError("成交量均线周期应在 1 到 500 之间")
        if not 0 <= vol_mult <= 100:
            raise ValueError("放量倍数应在 0 到 100 之间")
        if not 0 <= cooldown_bars <= 100:
            raise ValueError("信号冷却根数应在 0 到 100 之间")
        if dir_mode not in DIR_MODES:
            # 拼错时静默退化成双向，会让用户以为在做单边
            raise ValueError(f"方向模式只能是 {' / '.join(DIR_MODES)} 之一，当前为 {dir_mode!r}")

        # ── Extract price series ───────────────────────────────────────
        n = len(klines)
        if n == 0:
            return IndicatorResult(
                type=self.type, params=params, values=[], render=self._render(),
            )

        closes = _get_closes(klines)
        highs = _get_highs(klines)
        lows = _get_lows(klines)
        times = _get_times(klines)
        vols = [float(k.get("volume") or 0) for k in klines]

        # ── ATR: 真实波幅 → Wilder 平滑(RMA) ───────────────────────────
        # 用 RMA 而不是 EMA：两者 alpha 不同(1/n vs 2/(n+1))，EMA 口径下
        # ATR 的反应速度约为标准的 1.87 倍，会连带改变"刺穿过深/过浅"的两道门限。
        atr = _atr(highs, lows, closes, atr_len)

        # ── Volume average ─────────────────────────────────────────────
        vol_avg = _sma(vols, vol_len)

        # ── 03 · SWING LEVEL TRACKING ──────────────────────────────────
        # Each level stored as (price, bar_index)
        low_levels: list[tuple[float, int]] = []
        high_levels: list[tuple[float, int]] = []

        # ── 04 · PENDING SWEEP STATE ───────────────────────────────────
        p_low_lvl: float | None = None
        p_low_arm: int | None = None
        p_low_ext: float | None = None
        p_low_bar: int | None = None

        p_high_lvl: float | None = None
        p_high_arm: int | None = None
        p_high_ext: float | None = None
        p_high_bar: int | None = None

        last_sig_bar: int | None = None

        # ── OUTPUT arrays ──────────────────────────────────────────────
        bull_signals: list[float] = [0.0] * n
        bear_signals: list[float] = [0.0] * n
        bull_levels: list[float] = [0.0] * n
        bear_levels: list[float] = [0.0] * n

        # ── Helper: depth gate ─────────────────────────────────────────
        def depth_ok(depth: float, bar_atr: float | None) -> bool:
            # ATR 未定义（预热期）时不发信号：原版 Pine 是 `not na(atr)`，
            # 拿 0 顶上会让整段预热期照常出信号，而参考脚本一根都不出。
            if bar_atr is None or bar_atr <= 0:
                return False
            if depth < min_wick_atr * bar_atr:
                return False
            if max_wick_atr > 0 and depth > max_wick_atr * bar_atr:
                return False
            return True

        # ── Helper: find nearest swept low ─────────────────────────────
        # Returns (index, level, orig_bar) or None
        def nearest_low(lo: float) -> tuple[int, float, int] | None:
            best_idx = -1
            best_v: float | None = None
            for j, (v, _b) in enumerate(low_levels):
                if lo < v and (best_idx == -1 or v > best_v):  # type: ignore[operator]
                    best_v = v
                    best_idx = j
            if best_idx >= 0:
                return best_idx, low_levels[best_idx][0], low_levels[best_idx][1]
            return None

        # ── Helper: find nearest swept high ────────────────────────────
        def nearest_high(hi: float) -> tuple[int, float, int] | None:
            best_idx = -1
            best_v: float | None = None
            for j, (v, _b) in enumerate(high_levels):
                if hi > v and (best_idx == -1 or v < best_v):  # type: ignore[operator]
                    best_v = v
                    best_idx = j
            if best_idx >= 0:
                return best_idx, high_levels[best_idx][0], high_levels[best_idx][1]
            return None

        # ═══════════════════════════════════════════════════════════════
        # MAIN LOOP: process bar-by-bar (mirrors Pine Script execution)
        # ═══════════════════════════════════════════════════════════════
        for i in range(n):
            # ── Expire old levels ──────────────────────────────────────
            low_levels = [(p, b) for p, b in low_levels if i - b <= max_level_age]
            high_levels = [(p, b) for p, b in high_levels if i - b <= max_level_age]

            # ── Detect new pivot lows ─────────────────────────────────
            if piv_len <= i < n - piv_len:
                left_lows = lows[i - piv_len:i]
                right_lows = lows[i + 1:i + piv_len + 1]
                if lows[i] < min(left_lows) and lows[i] < min(right_lows):
                    low_levels.append((lows[i], i))
                    while len(low_levels) > max_levels:
                        low_levels.pop(0)

                # ── Detect new pivot highs ────────────────────────────
                left_highs = highs[i - piv_len:i]
                right_highs = highs[i + 1:i + piv_len + 1]
                if highs[i] > max(left_highs) and highs[i] > max(right_highs):
                    high_levels.append((highs[i], i))
                    while len(high_levels) > max_levels:
                        high_levels.pop(0)

            # ── Per-bar sweep detection ────────────────────────────────
            bull_sweep = False
            bull_level: float | None = None
            bull_ext: float | None = None
            bull_lvl_bar: int | None = None

            bear_sweep = False
            bear_level: float | None = None
            bear_ext: float | None = None
            bear_lvl_bar: int | None = None

            bar_atr = atr[i] if i < len(atr) else None

            # ── BULL sweep: pending completion ─────────────────────────
            if p_low_lvl is not None:
                p_low_ext = min(p_low_ext, lows[i])  # type: ignore[arg-type]
                if closes[i] > p_low_lvl:
                    bull_sweep = True
                    bull_level = p_low_lvl
                    bull_ext = p_low_ext
                    bull_lvl_bar = p_low_bar
                    p_low_lvl = None
                    p_low_arm = None
                    p_low_ext = None
                    p_low_bar = None
                elif i - p_low_arm >= reclaim_win:  # type: ignore[operator]
                    # Expired — reclaim window passed
                    p_low_lvl = None
                    p_low_arm = None
                    p_low_ext = None
                    p_low_bar = None

            # ── BULL sweep: new initiation ─────────────────────────────
            if p_low_lvl is None and not bull_sweep:
                result = nearest_low(lows[i])
                if result is not None:
                    idx, lvl, obar = result
                    depth = lvl - lows[i]
                    if depth_ok(depth, bar_atr) and highs[i] >= lvl:
                        del low_levels[idx]  # consume the level
                        if closes[i] > lvl:
                            # Same-bar sweep + reclaim → signal
                            bull_sweep = True
                            bull_level = lvl
                            bull_ext = lows[i]
                            bull_lvl_bar = obar
                        elif reclaim_win > 0:
                            # Swept but not reclaimed → pending
                            p_low_lvl = lvl
                            p_low_arm = i
                            p_low_ext = lows[i]
                            p_low_bar = obar

            # ── BEAR sweep: pending completion ─────────────────────────
            if p_high_lvl is not None:
                p_high_ext = max(p_high_ext, highs[i])  # type: ignore[arg-type]
                if closes[i] < p_high_lvl:
                    bear_sweep = True
                    bear_level = p_high_lvl
                    bear_ext = p_high_ext
                    bear_lvl_bar = p_high_bar
                    p_high_lvl = None
                    p_high_arm = None
                    p_high_ext = None
                    p_high_bar = None
                elif i - p_high_arm >= reclaim_win:  # type: ignore[operator]
                    p_high_lvl = None
                    p_high_arm = None
                    p_high_ext = None
                    p_high_bar = None

            # ── BEAR sweep: new initiation ─────────────────────────────
            if p_high_lvl is None and not bear_sweep:
                result = nearest_high(highs[i])
                if result is not None:
                    idx, lvl, obar = result
                    depth = highs[i] - lvl
                    if depth_ok(depth, bar_atr) and lows[i] <= lvl:
                        del high_levels[idx]
                        if closes[i] < lvl:
                            bear_sweep = True
                            bear_level = lvl
                            bear_ext = highs[i]
                            bear_lvl_bar = obar
                        elif reclaim_win > 0:
                            p_high_lvl = lvl
                            p_high_arm = i
                            p_high_ext = highs[i]
                            p_high_bar = obar

            # ═══════════════════════════════════════════════════════════
            # FILTERS → FINAL SIGNALS
            # ═══════════════════════════════════════════════════════════
            if bull_sweep or bear_sweep:
                # Volume gate：成交量均线样本不足时无法判断“放量”，该扫描不成立
                vol_ok = True
                if use_vol:
                    va = vol_avg[i] if i < len(vol_avg) else None
                    vol_ok = va is not None and va > 0 and vols[i] >= va * vol_mult

                # Dual-side block
                dual_blocked = block_dual and bull_sweep and bear_sweep

                # Direction mode
                dir_bull = dir_mode != "Short Only"
                dir_bear = dir_mode != "Long Only"

                # Cooldown
                cooldown_ok = last_sig_bar is None or (i - last_sig_bar) >= cooldown_bars

                # ATR valid（预热期为 None → 不发信号）
                atr_ok = bar_atr is not None and bar_atr > 0

                final_bull = (
                    bull_sweep and not dual_blocked and vol_ok
                    and dir_bull and atr_ok and cooldown_ok
                )
                final_bear = (
                    bear_sweep and not dual_blocked and vol_ok
                    and dir_bear and atr_ok and cooldown_ok
                )

                # Same-bar dual signal → discard both
                if final_bull and final_bear:
                    final_bull = False
                    final_bear = False

                if final_bull:
                    bull_signals[i] = 1.0
                    bull_levels[i] = bull_level if bull_level is not None else 0.0
                    last_sig_bar = i

                if final_bear:
                    bear_signals[i] = -1.0
                    bear_levels[i] = bear_level if bear_level is not None else 0.0
                    last_sig_bar = i

        # ═══════════════════════════════════════════════════════════════
        # BUILD OUTPUT VALUES
        # ═══════════════════════════════════════════════════════════════
        values: list[dict[str, Any]] = []
        for i in range(n):
            values.append({
                "time": float(times[i]),
                "atr": None if atr[i] is None else round(atr[i], 8),
                "bull_signal": bull_signals[i],
                "bear_signal": bear_signals[i],
                "bull_level": round(bull_levels[i], 8),
                "bear_level": round(bear_levels[i], 8),
            })

        return IndicatorResult(
            type=self.type,
            params={
                "piv_len": piv_len, "reclaim_win": reclaim_win,
                "atr_len": atr_len, "max_levels": max_levels,
                "max_level_age": max_level_age, "dir_mode": dir_mode,
                "min_wick_atr": min_wick_atr, "max_wick_atr": max_wick_atr,
                "use_vol": use_vol, "vol_len": vol_len, "vol_mult": vol_mult,
                "block_dual": block_dual, "cooldown_bars": cooldown_bars,
            },
            values=values,
            render=self._render(),
        )

    @staticmethod
    def _render() -> RenderSpec:
        """信号用**标记**呈现，不画成线。

        这里原来是两条 `line` plot，字段值是 `bull_signal ∈ {0,1}` /
        `bear_signal ∈ {-1,0}`——也就是把"事件标记"当成了连续序列画进主图。
        两个后果：

        1. 前端给主图叠加线时没有设 `priceScaleId`，所有主图 series 共用右侧
           价格轴并取数据范围并集，于是价格轴要同时容纳 -1 和 12 附近的报价，
           **K 线被压扁到顶部一小条**（本仓库其余指标的主图叠加线都是价格量级，
           非价格序列一律走副图）。
        2. 即使不压扁，0/1 在 0 和 1 之间来回跳也读不出任何信息。

        改用 marker，并把标记**挂在被扫的那个价位上**（`price_field`），
        复刻参考脚本"被扫流动性水平线 + SSL/BSL SWEEP 标签"传达的信息：
        SSL＝卖方流动性（低点下方）被扫 → 看涨；BSL＝买方流动性（高点上方）被扫 → 看跌。
        MarkerSpec 会挂到 K 线 series 上，不参与价格轴缩放。
        """
        # 配色跟随本应用的涨跌约定（红涨绿跌，与 K 线 upColor/downColor 同族），
        # 而不是参考脚本的西方约定（青＝涨、品红＝跌）——否则这张图上的颜色
        # 与页面其它地方的涨跌含义正好相反。
        return RenderSpec(window="main", markers=[
            MarkerSpec(
                field="bull_signal", price_field="bull_level",
                buy_color=BULL_COLOR, sell_color=BULL_COLOR, buy_label="SSL SWEEP",
                size=1,
            ),
            MarkerSpec(
                field="bear_signal", price_field="bear_level",
                buy_color=BEAR_COLOR, sell_color=BEAR_COLOR, sell_label="BSL SWEEP",
                size=1,
            ),
        ])
