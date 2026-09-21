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

    async def evaluate_groups(self, groups, logic, primary_tf, kline_data, chan_data, indicator_data):
        return len(kline_data[primary_tf]) == 125


def test_backtest_with_risk_disabled_waits_for_condition_exit_beyond_100_bars():
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
