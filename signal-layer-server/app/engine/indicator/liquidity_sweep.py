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
  - HTF cross-timeframe lookup (use_htf treated as always True)
"""

from app.engine.indicator.base import (
    IndicatorCalculator, IndicatorResult, RenderSpec, PlotSpec,
    _get_closes, _get_highs, _get_lows, _get_times, _ema, _sma,
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
        piv_len = int(params.get("piv_len", 8))
        reclaim_win = int(params.get("reclaim_win", 1))
        atr_len = int(params.get("atr_len", 14))
        max_levels = int(params.get("max_levels", 12))
        max_level_age = int(params.get("max_level_age", 600))
        dir_mode = str(params.get("dir_mode", "Both"))  # "Both" | "Long Only" | "Short Only"

        # ── 02 · FILTER Params ──────────────────────────────────────────
        min_wick_atr = float(params.get("min_wick_atr", 0.15))
        max_wick_atr = float(params.get("max_wick_atr", 2.5))
        use_vol = bool(params.get("use_vol", False))
        vol_len = int(params.get("vol_len", 20))
        vol_mult = float(params.get("vol_mult", 1.5))
        use_htf = bool(params.get("use_htf", True))      # accepted but not used (Phase 2)
        htf_ema_len = int(params.get("htf_ema_len", 50))  # accepted but not used (Phase 2)
        block_dual = bool(params.get("block_dual", True))
        cooldown_bars = int(params.get("cooldown_bars", 3))

        # ── Extract price series ───────────────────────────────────────
        n = len(klines)
        if n == 0:
            return IndicatorResult(
                type=self.type, params=params, values=[],
                render=RenderSpec(window="main", plots=[
                    PlotSpec(field="bull_signal", type="line", color="#00E5C0", label="BUY"),
                    PlotSpec(field="bear_signal", type="line", color="#FF2E93", label="SELL"),
                ]),
            )

        closes = _get_closes(klines)
        highs = _get_highs(klines)
        lows = _get_lows(klines)
        times = _get_times(klines)
        vols = [float(k.get("volume") or 0) for k in klines]

        # ── ATR: True Range → EMA ──────────────────────────────────────
        tr: list[float] = []
        for i in range(n):
            if i == 0:
                tr.append(highs[i] - lows[i])
            else:
                tr.append(max(
                    highs[i] - lows[i],
                    abs(highs[i] - closes[i - 1]),
                    abs(lows[i] - closes[i - 1]),
                ))
        atr = _ema(tr, atr_len)

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
        def depth_ok(depth: float, bar_atr: float) -> bool:
            if bar_atr <= 0:
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

            bar_atr = atr[i] if i < len(atr) else 0.0

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
                # Volume gate
                vol_ok = True
                if use_vol:
                    va = vol_avg[i] if i < len(vol_avg) else 0
                    vol_ok = va > 0 and vols[i] >= va * vol_mult

                # Dual-side block
                dual_blocked = block_dual and bull_sweep and bear_sweep

                # HTF trend: skip cross-timeframe lookup per Phase 1 spec
                htf_bull = True
                htf_bear = True

                # Direction mode
                dir_bull = dir_mode != "Short Only"
                dir_bear = dir_mode != "Long Only"

                # Cooldown
                cooldown_ok = last_sig_bar is None or (i - last_sig_bar) >= cooldown_bars

                # ATR valid
                atr_ok = bar_atr > 0

                final_bull = (
                    bull_sweep and not dual_blocked and vol_ok
                    and htf_bull and dir_bull and atr_ok and cooldown_ok
                )
                final_bear = (
                    bear_sweep and not dual_blocked and vol_ok
                    and htf_bear and dir_bear and atr_ok and cooldown_ok
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
        values: list[dict[str, float]] = []
        for i in range(n):
            values.append({
                "time": float(times[i]),
                "atr": round(atr[i], 8) if i < len(atr) else 0.0,
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
                "use_htf": use_htf, "htf_ema_len": htf_ema_len,
                "block_dual": block_dual, "cooldown_bars": cooldown_bars,
            },
            values=values,
            render=RenderSpec(
                window="main",
                plots=[
                    PlotSpec(field="bull_signal", type="line", color="#00E5C0", label="BUY"),
                    PlotSpec(field="bear_signal", type="line", color="#FF2E93", label="SELL"),
                ],
            ),
        )
