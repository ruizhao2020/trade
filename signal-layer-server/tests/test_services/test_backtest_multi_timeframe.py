"""回测必须看不到未来数据，且要能拿到所有级别的数据。

覆盖两点：
1. `_chan_until` 按当前主周期K线截断缠论结构（否则一买计数会把之后才形成的算进来）；
2. 次级周期条件所需的级别都会被纳入取数集合。
"""

import asyncio

from app.engine.chan import ChanResult
from app.engine.chan.signal import BuySellPoint
from app.schemas.signal import ConditionGroupSchema, ConditionSchema, ConditionTemplateSchema
from app.services.backtest_service import _chan_until
from app.services.signal_evaluation_service import _collect_requirements

BASE_TIME = 1_700_000_000_000
DAY_MS = 86_400_000


def _buy_point(time: int, kind: str = "buy1") -> BuySellPoint:
    return BuySellPoint(
        type=kind, price=10.0, time=time,
        zhongshu_index=None, bi_index=0, confirmed=True, strength=1.0,
    )


def _chan(*buy_times: int) -> ChanResult:
    return ChanResult(
        symbol="000001_sz", timeframe="1d",
        merged_klines=[], fenxings=[], bis=[], duans=[],
        zhongshus=[], duan_zhongshus=[],
        buy_sell_points=[_buy_point(time) for time in buy_times],
        divergences=[], updated_at=BASE_TIME,
    )


def test_chan_until_drops_structures_formed_after_the_current_bar():
    """在第 5 根时，第 10 根才形成的一买不应被计入。"""
    result = _chan(BASE_TIME + 3 * DAY_MS, BASE_TIME + 10 * DAY_MS)

    early = _chan_until(result, BASE_TIME + 5 * DAY_MS)
    late = _chan_until(result, BASE_TIME + 10 * DAY_MS)

    assert [p.time for p in early.buy_sell_points] == [BASE_TIME + 3 * DAY_MS]
    assert len(late.buy_sell_points) == 2


def test_chan_until_handles_missing_result():
    assert _chan_until(None, BASE_TIME) is None


def _secondary_template(secondaries: list[str]) -> ConditionTemplateSchema:
    return ConditionTemplateSchema.model_validate({
        "id": "tpl", "name": "次级", "logic": "AND", "primary_tf": "1d",
        "secondary_tfs": secondaries,
        "condition_groups": [{
            "id": "g1",
            "conditions": [{
                "id": "c1", "name": "次级周期一买",
                "left": {"source": "chan", "element": "buySellPoint", "property": "buy1"},
                "operator": "gt",
                "right": {"source": "constant", "value": 0},
                "timeframe_id": "secondary",
            }],
        }],
    })


def test_secondary_condition_pulls_every_declared_level():
    template = _secondary_template(["60m", "30m"])

    timeframes, _ = _collect_requirements(template, list(template.condition_groups))

    assert set(timeframes) >= {"1d", "60m", "30m"}


def test_secondary_condition_without_levels_adds_nothing_extra():
    template = _secondary_template([])

    timeframes, _ = _collect_requirements(template, list(template.condition_groups))

    assert timeframes == ["1d"]


def test_indicator_requirements_are_registered_per_secondary_level():
    """次级周期条件引用的指标要在每个次级级别上分别计算。"""
    template = ConditionTemplateSchema.model_validate({
        "id": "tpl", "name": "次级", "logic": "AND", "primary_tf": "1d",
        "secondary_tfs": ["60m", "30m"],
        "condition_groups": [{
            "id": "g1",
            "conditions": [{
                "id": "c1", "name": "次级周期 MA5",
                "left": {"source": "indicator", "indicator_type": "ma", "params": {"period": 5}},
                "operator": "gt",
                "right": {"source": "constant", "value": 0},
                "timeframe_id": "secondary",
            }],
        }],
    })

    timeframes, indicators = _collect_requirements(template, list(template.condition_groups))

    assert set(timeframes) >= {"1d", "60m", "30m"}
    assert indicators.get("60m"), "60分钟缺少指标需求"
    assert indicators.get("30m"), "30分钟缺少指标需求"
