import logging
from bisect import bisect_right
from dataclasses import replace

from app.schemas.signal import (
    ConditionTemplateSchema, TradeParams,
    BacktestResult, OpenPosition, TradeRecord,
)
from app.services.condition_service import ConditionService

logger = logging.getLogger(__name__)


def _chan_until(result, current_time: int):
    """只保留截至 current_time 已经确认的缠论结构。

    缠论是在整段 K 线上一次性算出来的，直接拿去逐根回测会把当前K线之后才
    形成的一买/中枢也算进计数，等于用了未来数据。这里按元素结束时间截断。
    """
    if result is None:
        return None
    return replace(
        result,
        fenxings=[fx for fx in result.fenxings if fx.merged_kline.dt <= current_time],
        bis=[bi for bi in result.bis if bi.end_time <= current_time],
        duans=[duan for duan in result.duans if duan.end_time <= current_time],
        zhongshus=[zs for zs in result.zhongshus if zs.end_time <= current_time],
        duan_zhongshus=[zs for zs in result.duan_zhongshus if zs.end_time <= current_time],
        buy_sell_points=[p for p in result.buy_sell_points if p.time <= current_time],
        divergences=[d for d in result.divergences if d.time <= current_time],
    )


def _kelly_metrics(trades: list[TradeRecord]) -> tuple[float, float]:
    """返回平均盈亏比与完整凯利仓位百分比，结果限制在0%到100%。"""
    wins = [trade.pnl_pct for trade in trades if trade.pnl_pct > 0]
    losses = [abs(trade.pnl_pct) for trade in trades if trade.pnl_pct < 0]
    if not trades or not wins:
        return 0.0, 0.0
    if not losses:
        return 999.0, 100.0
    average_win = sum(wins) / len(wins)
    average_loss = sum(losses) / len(losses)
    payoff_ratio = average_win / average_loss if average_loss > 0 else 0.0
    if payoff_ratio <= 0:
        return 0.0, 0.0
    win_probability = len(wins) / len(trades)
    loss_probability = 1 - win_probability
    kelly = win_probability - loss_probability / payoff_ratio
    return round(payoff_ratio, 2), round(min(max(kelly, 0.0), 1.0) * 100, 1)


def _indicator_values_until(values: list[dict], current_time: int) -> list[dict]:
    """按时间而不是数组下标截断指标，兼容筹码快照及跨周期指标。"""
    return [
        value for value in values
        if int(float(value.get("time", 0))) <= current_time
    ]


class BacktestService:
    def __init__(self, condition_service: ConditionService):
        self._cond = condition_service

    async def run(
        self,
        symbol: str,
        template: ConditionTemplateSchema,
        kline_data: dict[str, list[dict]],
        chan_data: dict,
        indicator_data: dict[str, dict[str, list[dict]]],
        kline_limit: int = 500,
    ) -> BacktestResult:
        tp = template.trade_params or TradeParams()
        tf = template.primary_tf or "1d"
        klines = kline_data.get(tf, [])
        if len(klines) < 10:
            return BacktestResult(
                template_id=template.id, symbol=symbol, timeframe=tf,
                total_trades=0, win_trades=0, win_rate=0,
                total_return=0, avg_return=0, max_drawdown=0, profit_factor=0,
                payoff_ratio=0, suggested_position=0,
                trades=[],
            )

        trades: list[TradeRecord] = []
        in_position = False
        entry_price = 0.0
        stop_loss: float | None = None
        take_profit: float | None = None
        entry_bar = 0
        side = "long"

        highs = [float(k["high"]) for k in klines]
        lows = [float(k["low"]) for k in klines]
        closes = [float(k["close"]) for k in klines]

        # 各周期的时间轴（升序），用于按当前主周期K线快速定位截断点
        series_times = {
            name: [int(item["open_time"]) for item in series]
            for name, series in kline_data.items()
        }

        for i in range(20, len(klines)):
            current_time = int(klines[i]["open_time"])
            # 所有级别都截断到当前主周期K线，这样次级周期条件拿到的是
            # "该K线时间范围内最后一根已收盘K线"，不会看到未来数据。
            bar_kline_data = {
                name: series[:bisect_right(series_times[name], current_time)]
                for name, series in kline_data.items()
            }
            bar_chan = {}
            for name, chan in chan_data.items():
                truncated = _chan_until(chan, current_time)
                if truncated is not None:
                    bar_chan[name] = truncated
            bar_ind = {}
            for ind_tf, ind_map in indicator_data.items():
                bar_ind[ind_tf] = {}
                for ind_type, vals in ind_map.items():
                    bar_ind[ind_tf][ind_type] = _indicator_values_until(vals, current_time)

            if in_position:
                bars_held = i - entry_bar
                # 到期平仓：只有显式配置了持仓上限才生效（0 = 不限）。
                # 以前这里写死 100 根、并且对"止损止盈关闭 + 有出场条件"额外豁免，
                # 导致同样的"关闭"设置在不同配置下行为不同、界面上也看不到这条规则。
                max_hold_bars = int(getattr(tp, "max_hold_bars", 0) or 0)
                if max_hold_bars > 0 and bars_held > max_hold_bars:
                    pnl = (closes[i] - entry_price) / entry_price * 100
                    trades.append(TradeRecord(
                        entry_time=int(klines[entry_bar]["open_time"]),
                        exit_time=int(klines[i]["open_time"]),
                        side=side,
                        entry_price=round(entry_price, 2), exit_price=round(closes[i], 2),
                        pnl_pct=round(pnl, 2), exit_reason="timeout",
                    ))
                    in_position = False
                elif stop_loss is not None and lows[i] <= stop_loss:
                    pnl = (stop_loss - entry_price) / entry_price * 100
                    trades.append(TradeRecord(
                        entry_time=int(klines[entry_bar]["open_time"]),
                        exit_time=int(klines[i]["open_time"]),
                        side=side,
                        entry_price=round(entry_price, 2), exit_price=round(stop_loss, 2),
                        pnl_pct=round(pnl, 2), exit_reason="stop_loss",
                    ))
                    in_position = False
                elif take_profit is not None and highs[i] >= take_profit:
                    pnl = (take_profit - entry_price) / entry_price * 100
                    trades.append(TradeRecord(
                        entry_time=int(klines[entry_bar]["open_time"]),
                        exit_time=int(klines[i]["open_time"]),
                        side=side,
                        entry_price=round(entry_price, 2), exit_price=round(take_profit, 2),
                        pnl_pct=round(pnl, 2), exit_reason="take_profit",
                    ))
                    in_position = False
                elif tp.exit_conditions:
                    # 条件式出场：出场条件满足 → 按收盘价平仓
                    should_exit = await self._cond.evaluate_groups(
                        tp.exit_conditions, tp.exit_logic, tf,
                        bar_kline_data, bar_chan, bar_ind,
                        secondary_tfs=list(template.secondary_tfs or []),
                    )
                    if should_exit:
                        pnl = (closes[i] - entry_price) / entry_price * 100
                        trades.append(TradeRecord(
                            entry_time=int(klines[entry_bar]["open_time"]),
                            exit_time=int(klines[i]["open_time"]),
                            side=side,
                            entry_price=round(entry_price, 2), exit_price=round(closes[i], 2),
                            pnl_pct=round(pnl, 2), exit_reason="condition",
                        ))
                        in_position = False
                continue

            result = await self._cond.evaluate(
                template, bar_kline_data, bar_chan, bar_ind,
            )
            if not result.is_ready:
                continue

            entry_price = closes[i]
            entry_bar = i
            side = "long"
            in_position = True

            if tp.stop_loss_type == "none":
                stop_loss = None
            elif tp.stop_loss_type == "fixed_pct":
                stop_loss = entry_price * (1 - tp.stop_loss_value / 100)
            elif tp.stop_loss_type == "swing_low":
                stop_loss = min(lows[max(0, i - 20):i + 1])
            else:
                tr = _atr(highs, lows, closes, 14, i)
                stop_loss = entry_price - tr * tp.stop_loss_value

            if tp.take_profit_type == "none":
                take_profit = None
            elif tp.take_profit_type == "fixed_pct":
                take_profit = entry_price * (1 + tp.take_profit_value / 100)
            elif tp.take_profit_type == "rr_ratio":
                take_profit = (
                    entry_price + (entry_price - stop_loss) * tp.take_profit_value
                    if stop_loss is not None else None
                )
            else:
                tr = _atr(highs, lows, closes, 14, i)
                take_profit = entry_price + tr * tp.take_profit_value

        total = len(trades)
        wins = sum(1 for t in trades if t.pnl_pct > 0)
        win_rate = round(wins / total * 100, 1) if total > 0 else 0
        total_return = round(sum(t.pnl_pct for t in trades), 2)
        avg_return = round(total_return / total, 2) if total > 0 else 0

        cum = 0.0
        peak = 0.0
        max_dd = 0.0
        for t in trades:
            cum += t.pnl_pct
            if cum > peak:
                peak = cum
            dd = peak - cum
            if dd > max_dd:
                max_dd = dd
        max_drawdown = round(max_dd, 2)

        win_pnl = sum(t.pnl_pct for t in trades if t.pnl_pct > 0)
        loss_pnl = abs(sum(t.pnl_pct for t in trades if t.pnl_pct < 0))
        profit_factor = round(win_pnl / loss_pnl, 2) if loss_pnl > 0 else (999 if win_pnl > 0 else 0)
        payoff_ratio, suggested_position = _kelly_metrics(trades)

        # 区间结束时还在仓位里：单独报出来。统计口径保持"只算已平仓"，
        # 但界面和图表需要知道这笔还在（否则只设入场条件的策略看起来毫无信号）。
        open_position = None
        if in_position:
            last = len(klines) - 1
            last_close = closes[last]
            open_position = OpenPosition(
                entry_time=int(klines[entry_bar]["open_time"]),
                entry_price=round(entry_price, 2),
                side=side,
                bars_held=last - entry_bar,
                last_time=int(klines[last]["open_time"]),
                last_price=round(last_close, 2),
                pnl_pct=round((last_close - entry_price) / entry_price * 100, 2),
            )

        return BacktestResult(
            template_id=template.id, symbol=symbol, timeframe=tf,
            total_trades=total, win_trades=wins, win_rate=win_rate,
            total_return=total_return, avg_return=avg_return,
            max_drawdown=max_drawdown, profit_factor=profit_factor,
            payoff_ratio=payoff_ratio, suggested_position=suggested_position,
            trades=trades, open_position=open_position,
        )


def _atr(highs, lows, closes, period, i):
    tr_sum = 0.0
    count = min(period, i + 1)
    if count == 0:
        return 0.0
    for j in range(i - count + 1, i + 1):
        prev_close = closes[j - 1] if j > 0 else closes[j]
        tr = max(highs[j] - lows[j], abs(highs[j] - prev_close), abs(lows[j] - prev_close))
        tr_sum += tr
    return tr_sum / count
