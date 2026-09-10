from types import SimpleNamespace

from app.schemas.signal import ChanValue, ConditionSchema, ConstantValue, IndicatorValue, TimeframeValue
from app.services.condition_service import ConditionService
from app.services.signal_evaluation_service import indicator_data_key, required_kline_limit


def test_between_operator_accepts_reversed_bounds():
    service = ConditionService()
    assert service._compare(5, "between", 10, right2=1)
    assert not service._compare(11, "between", 10, right2=1)


def test_ma_direction_operators_compare_with_previous_value():
    service = ConditionService()
    assert service._compare(11, "rising", 0, prev_left=10)
    assert not service._compare(10, "rising", 0, prev_left=10)
    assert service._compare(9, "falling", 0, prev_left=10)
    assert not service._compare(10, "falling", 0, prev_left=10)


def test_ma_direction_reversal_operators_require_a_slope_change():
    service = ConditionService()
    assert service._compare(10, "turnDown", 0, prev_left=11, prev_prev_left=9)
    assert not service._compare(12, "turnDown", 0, prev_left=11, prev_prev_left=9)
    assert not service._compare(10, "turnDown", 0, prev_left=11, prev_prev_left=12)

    assert service._compare(12, "turnUp", 0, prev_left=10, prev_prev_left=11)
    assert not service._compare(9, "turnUp", 0, prev_left=10, prev_prev_left=11)
    assert not service._compare(12, "turnUp", 0, prev_left=10, prev_prev_left=9)


def test_condition_schema_accepts_direction_operators():
    for operator in ("rising", "falling", "turnDown", "turnUp"):
        condition = ConditionSchema.model_validate({
            "id": f"condition-{operator}",
            "name": "均线方向",
            "left": {"source": "indicator", "indicator_type": "ma", "params": {"period": 120}},
            "operator": operator,
            "right": {"source": "constant", "value": 0},
        })
        assert condition.operator == operator


def test_chan_divergence_condition_filters_direction_and_confirmation():
    service = ConditionService()
    condition = ConditionSchema.model_validate({
        "id": "condition-bottom-divergence",
        "name": "底背驰",
        "left": {"source": "chan", "element": "divergence", "property": "bottom"},
        "operator": "gt",
        "right": {"source": "constant", "value": 0},
    })
    chan = SimpleNamespace(divergences=[
        SimpleNamespace(type="bottom", confirmed=True),
        SimpleNamespace(type="bottom", confirmed=False),
        SimpleNamespace(type="top", confirmed=True),
    ])

    value = service._resolve(
        ChanValue(source="chan", element="divergence", property="bottom"),
        condition,
        kline_data={},
        chan_data={"1d": chan},
        indicator_data={},
        default_tf="1d",
    )
    assert value == 1.0


def test_ma260_expands_realtime_kline_history():
    requirement = IndicatorValue(
        source="indicator",
        indicator_type="ma",
        params={"period": 260},
        field="value",
    )
    assert required_kline_limit(200, {indicator_data_key("ma", requirement.params): requirement}) == 261


def test_condition_accepts_legacy_right_2_alias():
    condition = ConditionSchema.model_validate({
        "id": "condition-between",
        "name": "区间",
        "left": {"source": "price", "field": "close"},
        "operator": "between",
        "right": {"source": "constant", "value": 1},
        "right_2": {"source": "constant", "value": 10},
        "enabled": True,
    })
    assert condition.right2 is not None
    assert condition.right2.value == 10


def test_indicator_resolution_distinguishes_parameters_and_timeframes():
    service = ConditionService()
    indicator = IndicatorValue(
        source="indicator",
        indicator_type="ma",
        params={"period": 20},
        field="value",
    )
    condition = ConditionSchema(
        id="condition-1",
        name="跨周期 MA20",
        left=TimeframeValue(source="timeframe", timeframe_id="30m", inner=indicator),
        operator="gt",
        right=ConstantValue(source="constant", value=0),
        enabled=True,
    )
    indicator_data = {
        "30m": {
            indicator_data_key("ma", {"period": 5}): [{"value": 5.0}],
            indicator_data_key("ma", indicator.params): [{"value": 20.0}],
        }
    }
    value = service._resolve(
        condition.left,
        condition,
        kline_data={},
        chan_data={},
        indicator_data=indicator_data,
        default_tf="1d",
    )
    assert value == 20.0
