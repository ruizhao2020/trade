import asyncio
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.template import update_template
from app.models.base import Base
from app.models.template import Template
from app.schemas.template import TemplateUpdate


def test_template_update_persists_disabled_risk_and_exit_conditions():
    async def scenario():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            session.add(Template(
                id="template-risk-update", user_id=7, name="均线拐头", logic="AND",
                condition_groups=[], primary_tf="1d", secondary_tfs=[], enabled=True,
                trade_params={
                    "stop_loss_type": "atr", "stop_loss_value": 3,
                    "take_profit_type": "rr_ratio", "take_profit_value": 2,
                    "exit_conditions": [], "exit_logic": "AND",
                },
            ))
            await session.commit()

            body = TemplateUpdate.model_validate({
                "trade_params": {
                    "stop_loss_type": "none", "stop_loss_value": 0,
                    "take_profit_type": "none", "take_profit_value": 0,
                    "exit_conditions": [{
                        "id": "exit-ma", "name": "MA5上转下", "logic": "AND",
                        "conditions": [{
                            "id": "turn-down", "name": "",
                            "left": {"source": "indicator", "indicator_type": "ma", "params": {"period": 5}},
                            "operator": "turnDown",
                            "right": {"source": "constant", "value": 0},
                        }],
                    }],
                    "exit_logic": "AND",
                },
            })
            response = await update_template(
                "template-risk-update", body, session, SimpleNamespace(id=7),
            )
            assert response.trade_params is not None
            assert response.trade_params.stop_loss_type == "none"
            assert response.trade_params.take_profit_type == "none"

        async with sessions() as verification_session:
            stored = await verification_session.get(Template, "template-risk-update")
            assert stored is not None
            assert stored.trade_params["stop_loss_type"] == "none"
            assert stored.trade_params["take_profit_type"] == "none"
            assert stored.trade_params["exit_conditions"][0]["name"] == "MA5上转下"
        await engine.dispose()

    asyncio.run(scenario())
