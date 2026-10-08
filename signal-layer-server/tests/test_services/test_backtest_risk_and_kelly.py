from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.schemas.signal import ConditionTemplateSchema, TradeRecord
from app.services.backtest_service import BacktestService, _kelly_metrics


def trade(pnl: float) -> TradeRecord:
    return TradeRecord(
        entry_time=1, exit_time=2, side="long",
        entry_price=100, exit_price=100 + pnl,
        pnl_pct=pnl, exit_reason="condition",
    )


def test_kelly_position_uses_win_rate_and_average_payoff_ratio():
    payoff, position = _kelly_metrics([trade(10), trade(20), trade(-5), trade(-5)])
    assert payoff == 3.0
    assert position == 33.3


def test_kelly_position_is_clamped_to_valid_percent_range():
    assert _kelly_metrics([trade(-5), trade(-2)]) == (0.0, 0.0)
    assert _kelly_metrics([trade(5), trade(10)]) == (999.0, 100.0)


class ConditionOnlyService:
    async def evaluate(self, template, kline_data, chan_data, indicator_data):
        return SimpleNamespace(is_ready=len(kline_data[template.primary_tf]) == 21)

    async def evaluate_groups(
        self, groups, logic, primary_tf, kline_data, chan_data, indicator_data,
        secondary_tfs=None,
    ):
        return len(kline_data[primary_tf]) == 125


def test_backtest_with_risk_disabled_waits_for_condition_exit_beyond_100_bars():
    """止损止盈关闭且未设持仓上限（默认 0）→ 一直持有到出场条件满足。

    以前这里是靠"止损止盈都关 + 有出场条件"这个特例豁免 100 根强制平仓；
    现在改成显式的 max_hold_bars（默认 0＝不限），语义一致、界面上也看得见。
    """
    template = ConditionTemplateSchema.model_validate({
        "id": "condition-only", "name": "仅买卖点", "logic": "AND", "primary_tf": "1d",
        "condition_groups": [{
            "id": "entry", "conditions": [{
                "id": "buy", "name": "买点",
                "left": {"source": "constant", "value": 1}, "operator": "gt",
                "right": {"source": "constant", "value": 0},
            }],
        }],
        "trade_params": {
            "stop_loss_type": "none", "stop_loss_value": 0,
            "take_profit_type": "none", "take_profit_value": 0,
            "exit_conditions": [{
                "id": "exit", "conditions": [{
                    "id": "sell", "name": "卖点",
                    "left": {"source": "constant", "value": 1}, "operator": "gt",
                    "right": {"source": "constant", "value": 0},
                }],
            }],
        },
    })
    klines = [{
        "open_time": index, "open": 100, "high": 101, "low": 99,
        "close": 100 + index * 0.01, "volume": 100,
    } for index in range(130)]

    result = asyncio.run(BacktestService(ConditionOnlyService()).run(
        "000001_sz", template, {"1d": klines}, {}, {}, 130,
    ))

    assert result.total_trades == 1
    assert result.trades[0].exit_reason == "condition"
    assert result.trades[0].exit_time == 124


def _hold_template(max_hold_bars: int | None, *, with_exit_conditions: bool = False):
    trade_params: dict = {
        "stop_loss_type": "none", "stop_loss_value": 0,
        "take_profit_type": "none", "take_profit_value": 0,
    }
    if max_hold_bars is not None:
        trade_params["max_hold_bars"] = max_hold_bars
    if with_exit_conditions:
        trade_params["exit_conditions"] = [{
            "id": "exit", "conditions": [{
                "id": "sell", "name": "卖点",
                "left": {"source": "constant", "value": 1}, "operator": "gt",
                "right": {"source": "constant", "value": 0},
            }],
        }]
    return ConditionTemplateSchema.model_validate({
        "id": "hold", "name": "持仓上限", "logic": "AND", "primary_tf": "1d",
        "condition_groups": [{
            "id": "entry", "conditions": [{
                "id": "buy", "name": "买点",
                "left": {"source": "constant", "value": 1}, "operator": "gt",
                "right": {"source": "constant", "value": 0},
            }],
        }],
        "trade_params": trade_params,
    })


def _flat_klines(count: int) -> list[dict]:
    return [{
        "open_time": index, "open": 100, "high": 101, "low": 99,
        "close": 100 + index * 0.01, "volume": 100,
    } for index in range(count)]


def test_default_hold_limit_is_unlimited_so_positions_are_not_silently_closed():
    """默认 max_hold_bars=0 → 不做到期平仓。

    这正是「止损止盈都关闭、也没出场条件」时不该冒出「策略卖」的原因：
    没有平仓规则的持仓一直持到数据末尾，不产生任何出场。
    """
    template = _hold_template(None)   # 不传，走 schema 默认 0
    klines = _flat_klines(200)

    result = asyncio.run(BacktestService(ConditionOnlyService()).run(
        "000001_sz", template, {"1d": klines}, {}, {}, 200,
    ))

    assert result.total_trades == 0, "默认不该有任何到期平仓"


def test_explicit_hold_limit_closes_the_position():
    """显式配置持仓上限后才到期平仓，并在记录里标明原因。"""
    template = _hold_template(20)
    klines = _flat_klines(200)

    result = asyncio.run(BacktestService(ConditionOnlyService()).run(
        "000001_sz", template, {"1d": klines}, {}, {}, 200,
    ))

    assert result.total_trades == 1
    assert result.trades[0].exit_reason == "timeout"
    # 入场约在第 21 根（is_ready 之后），持有上限 20 根 → 第 41 根到期平仓
    assert result.trades[0].exit_time == 41


def test_hold_limit_also_applies_when_exit_conditions_exist():
    """配了出场条件也照样受持仓上限约束。

    旧实现有个隐藏特例：止损止盈关闭 + 有出场条件时豁免强制平仓，
    于是同样的"关闭"在不同配置下行为不同。现在它是显式参数，特例取消。
    """
    template = _hold_template(20, with_exit_conditions=True)
    klines = _flat_klines(200)

    result = asyncio.run(BacktestService(ConditionOnlyService()).run(
        "000001_sz", template, {"1d": klines}, {}, {}, 200,
    ))

    assert result.total_trades >= 1
    assert result.trades[0].exit_reason == "timeout"


def test_unclosed_position_is_reported_and_kept_out_of_realized_stats():
    """没有出场规则时，仓位一直开着：要报出来，但不能混进已完成交易的统计。

    真实案例：策略只配了入场条件（布林开口 + 中轨向上），止损止盈都关闭、
    也没设出场条件、持仓上限默认不限 —— 以前结果里 0 笔交易、累计收益 0，
    图上连买点都没有，看起来像策略完全没有信号。
    """
    template = _hold_template(None)   # 不传持仓上限，走 schema 默认 0（不限）
    klines = _flat_klines(200)

    result = asyncio.run(BacktestService(ConditionOnlyService()).run(
        "000001_sz", template, {"1d": klines}, {}, {}, 200,
    ))

    assert result.total_trades == 0
    open_position = result.open_position
    assert open_position is not None, "仍持仓必须被报出来，否则图上连买点都没有"

    # 入场在第 21 根（is_ready 之后），一直持到最后一根
    assert open_position.entry_time == klines[20]["open_time"]
    assert open_position.entry_price == round(klines[20]["close"], 2)
    assert open_position.last_time == klines[-1]["open_time"]
    assert open_position.last_price == round(klines[-1]["close"], 2)
    assert open_position.bars_held == len(klines) - 1 - 20
    expected_pnl = round(
        (klines[-1]["close"] - klines[20]["close"]) / klines[20]["close"] * 100, 2,
    )
    assert open_position.pnl_pct == expected_pnl

    # 浮动盈亏不是已实现收益：统计口径必须还是空的
    assert open_position.pnl_pct != 0
    assert result.total_return == 0
    assert result.win_rate == 0
    assert result.win_trades == 0
    assert result.profit_factor == 0


def test_no_open_position_when_everything_is_closed():
    """有出场规则、仓位已平掉时不报 open_position（避免界面多出一行"持有中"）。"""
    template = _hold_template(20)
    klines = _flat_klines(200)

    result = asyncio.run(BacktestService(ConditionOnlyService()).run(
        "000001_sz", template, {"1d": klines}, {}, {}, 200,
    ))

    assert result.total_trades == 1
    assert result.open_position is None


def test_open_position_absorbs_later_signals_while_holding():
    """仍在持仓时不会再开新仓：第二根之后的信号不该产生第二笔交易或第二个持仓。"""
    template = _hold_template(None)
    klines = _flat_klines(400)

    result = asyncio.run(BacktestService(ConditionOnlyService()).run(
        "000001_sz", template, {"1d": klines}, {}, {}, 400,
    ))

    assert result.total_trades == 0
    assert result.open_position is not None
    assert result.open_position.entry_time == klines[20]["open_time"]
    assert result.open_position.bars_held == len(klines) - 1 - 20
