"""交易模拟与统计。

口径严格对齐 services/backtest_service.py，保证"先用快速评估器搜索、
再用真实回测确认最优候选"两条路径得到的数字可比：
  - 逐笔收益求和作为总收益（不复利）
  - 回撤基于逐笔收益的累计曲线
  - 止损用 ATR 简单均值（非 Wilder）
  - 同一根K线同时触及止损与止盈时，按先止损处理（保守）

一次遍历产出逐笔交易，再从中派生整体统计与分段统计——搜索要跑成千上万个
候选，不能每个候选都重新遍历。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.engine.advisor.types import ExitSpec, LevelSeries, TradeStats

DEFAULT_TIMEOUT_BARS = 100
ATR_PERIOD = 14


@dataclass(frozen=True)
class Trade:
    entry_index: int
    exit_index: int
    pnl_pct: float


def atr_at(level: LevelSeries, index: int, period: int = ATR_PERIOD) -> float:
    """与 backtest_service._atr 相同的简单均值口径。"""
    count = min(period, index + 1)
    if count <= 0:
        return 0.0
    total = 0.0
    for offset in range(index - count + 1, index + 1):
        previous_close = level.closes[offset - 1] if offset > 0 else level.closes[offset]
        total += max(
            level.highs[offset] - level.lows[offset],
            abs(level.highs[offset] - previous_close),
            abs(level.lows[offset] - previous_close),
        )
    return total / count


def _entry_levels(level: LevelSeries, index: int, spec: ExitSpec, entry_price: float) -> tuple[float | None, float | None]:
    if spec.stop_loss_type == "none":
        stop_loss = None
    elif spec.stop_loss_type == "fixed_pct":
        stop_loss = entry_price * (1 - spec.stop_loss_value / 100)
    else:
        stop_loss = entry_price - atr_at(level, index) * spec.stop_loss_value

    if spec.take_profit_type == "none":
        take_profit = None
    elif spec.take_profit_type == "fixed_pct":
        take_profit = entry_price * (1 + spec.take_profit_value / 100)
    elif spec.take_profit_type == "rr_ratio":
        take_profit = (
            entry_price + (entry_price - stop_loss) * spec.take_profit_value
            if stop_loss is not None else None
        )
    else:
        take_profit = entry_price + atr_at(level, index) * spec.take_profit_value
    return stop_loss, take_profit


def simulate_trades(
    level: LevelSeries,
    entry_signal: list[bool],
    spec: ExitSpec,
    *,
    start: int = 0,
    end: int | None = None,
    timeout_bars: int = DEFAULT_TIMEOUT_BARS,
) -> list[Trade]:
    """在 [start, end) 区间内做多模拟，一次遍历产出逐笔交易。"""
    size = len(level.times)
    end = size if end is None else min(end, size)
    start = max(start, 0)
    trades: list[Trade] = []

    index = start
    while index < end:
        if not entry_signal[index]:
            index += 1
            continue

        entry_price = level.closes[index]
        if entry_price <= 0:
            index += 1
            continue
        stop_loss, take_profit = _entry_levels(level, index, spec, entry_price)

        exit_price: float | None = None
        exit_index = index
        for cursor in range(index + 1, end):
            if stop_loss is not None and level.lows[cursor] <= stop_loss:
                exit_price, exit_index = stop_loss, cursor
                break
            if take_profit is not None and level.highs[cursor] >= take_profit:
                exit_price, exit_index = take_profit, cursor
                break
            if cursor - index > timeout_bars:
                exit_price, exit_index = level.closes[cursor], cursor
                break

        if exit_price is None:
            # 区间末仍未平仓：按最后一根收盘价结算，避免虚增未完成交易
            exit_index = end - 1
            exit_price = level.closes[exit_index]

        trades.append(Trade(
            entry_index=index,
            exit_index=exit_index,
            pnl_pct=(exit_price - entry_price) / entry_price * 100,
        ))
        index = exit_index + 1 if exit_index >= index else index + 1

    return trades


def stats_from_trades(trades: list[Trade], bars: int) -> TradeStats:
    """从逐笔交易汇总统计；回撤按逐笔累计曲线（与 backtest_service 一致）。"""
    stats = TradeStats(bars=bars)
    cumulative = 0.0
    peak = 0.0
    for trade in trades:
        stats.trades += 1
        stats.total_return += trade.pnl_pct
        if trade.pnl_pct > 0:
            stats.wins += 1
            stats.gross_profit += trade.pnl_pct
        else:
            stats.gross_loss += abs(trade.pnl_pct)
        cumulative += trade.pnl_pct
        peak = max(peak, cumulative)
        stats.max_drawdown = max(stats.max_drawdown, peak - cumulative)

    stats.total_return = round(stats.total_return, 4)
    stats.gross_profit = round(stats.gross_profit, 4)
    stats.gross_loss = round(stats.gross_loss, 4)
    stats.max_drawdown = round(stats.max_drawdown, 4)
    return stats


def simulate(
    level: LevelSeries,
    entry_signal: list[bool],
    spec: ExitSpec,
    *,
    start: int = 0,
    end: int | None = None,
    timeout_bars: int = DEFAULT_TIMEOUT_BARS,
) -> TradeStats:
    """便捷封装：直接返回统计（内部仍是一次遍历）。"""
    size = len(level.times)
    end = size if end is None else min(end, size)
    start = max(start, 0)
    trades = simulate_trades(level, entry_signal, spec, start=start, end=end, timeout_bars=timeout_bars)
    return stats_from_trades(trades, max(0, end - start))
