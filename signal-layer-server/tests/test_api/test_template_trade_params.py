from app.api.template import _to_response
from app.models.template import Template
from app.schemas.template import TemplateCreate


def test_template_trade_params_round_trip_shape():
    trade_params = {
        "stop_loss_type": "atr",
        "stop_loss_value": 1.5,
        "take_profit_type": "rr_ratio",
        "take_profit_value": 2.0,
        "exit_conditions": [],
        "exit_logic": "AND",
    }
    parsed = TemplateCreate(
        id="template-1",
        name="测试策略",
        logic="AND",
        condition_groups=[],
        primary_tf="1d",
        trade_params=trade_params,
    )
    model = Template(
        id=parsed.id,
        name=parsed.name,
        logic=parsed.logic,
        condition_groups=parsed.condition_groups,
        primary_tf=parsed.primary_tf,
        secondary_tfs=[],
        enabled=True,
        trade_params=parsed.trade_params.model_dump(),
    )
    response = _to_response(model)
    assert response.trade_params is not None
    assert response.trade_params.stop_loss_value == 1.5
    assert not hasattr(response.trade_params, "position_value")


def test_condition_group_name_is_preserved_in_template_json():
    parsed = TemplateCreate(
        id="template-group-name",
        name="分组名称测试",
        logic="AND",
        condition_groups=[{
            "id": "group-1",
            "name": "趋势确认",
            "conditions": [],
        }],
        primary_tf="1d",
    )
    model = Template(
        id=parsed.id,
        name=parsed.name,
        logic=parsed.logic,
        condition_groups=parsed.condition_groups,
        primary_tf=parsed.primary_tf,
        secondary_tfs=[],
        enabled=True,
    )
    response = _to_response(model)
    assert response.condition_groups[0]["name"] == "趋势确认"


def test_disabled_stop_loss_and_take_profit_round_trip():
    parsed = TemplateCreate(
        id="template-no-risk",
        name="关闭止盈止损",
        logic="AND",
        condition_groups=[],
        primary_tf="1d",
        trade_params={
            "stop_loss_type": "none", "stop_loss_value": 0,
            "take_profit_type": "none", "take_profit_value": 0,
            "exit_conditions": [], "exit_logic": "AND",
        },
    )
    model = Template(
        id=parsed.id, name=parsed.name, logic=parsed.logic,
        condition_groups=[], primary_tf="1d", secondary_tfs=[], enabled=True,
        trade_params=parsed.trade_params.model_dump(),
    )
    response = _to_response(model)
    assert response.trade_params is not None
    assert response.trade_params.stop_loss_type == "none"
    assert response.trade_params.take_profit_type == "none"
