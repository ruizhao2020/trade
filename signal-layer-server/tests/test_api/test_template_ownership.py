"""策略归属：别人的模板即使 ID 猜到了也读不到、改不了，且报错文案是中文。

界面上曾出现过这种情况：切换账号后下拉里还留着上一个账号的策略，点编辑保存时报
404，而 detail 是英文的 "Template not found"，被前端原样显示出来。
归属校验本身是对的，这里把"拒绝 + 中文文案"一起钉住。
"""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.template import delete_template, get_template, update_template
from app.models.base import Base
from app.models.template import Template
from app.schemas.template import TemplateUpdate

OWNER_ID = 17
OTHER_ID = 1


async def _seeded_sessions():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        session.add(Template(
            id="tpl_owner", user_id=OWNER_ID, name="布林通道均线策略", logic="AND",
            condition_groups=[], primary_tf="1d", secondary_tfs=[], enabled=True,
            trade_params=None,
        ))
        await session.commit()
    return engine, sessions


def test_foreign_template_is_rejected_with_chinese_detail():
    async def scenario():
        engine, sessions = await _seeded_sessions()
        other = SimpleNamespace(id=OTHER_ID)
        async with sessions() as session:
            for call in (
                lambda: get_template("tpl_owner", session, other),
                lambda: update_template("tpl_owner", TemplateUpdate(name="改名"), session, other),
                lambda: delete_template("tpl_owner", session, other),
            ):
                with pytest.raises(HTTPException) as caught:
                    await call()
                assert caught.value.status_code == 404
                detail = caught.value.detail
                assert detail == "策略不存在或不属于当前账号"
                # 前端只在 detail 含中文时才直接展示；英文 detail 会退化成通用文案
                assert any("\u4e00" <= ch <= "\u9fff" for ch in detail)

        # 拒绝之后别人的策略必须原样还在
        async with sessions() as session:
            stored = await session.get(Template, "tpl_owner")
            assert stored is not None
            assert stored.user_id == OWNER_ID
            assert stored.name == "布林通道均线策略"
        await engine.dispose()

    asyncio.run(scenario())


def test_owner_can_still_update_own_template():
    async def scenario():
        engine, sessions = await _seeded_sessions()
        async with sessions() as session:
            response = await update_template(
                "tpl_owner", TemplateUpdate(name="我自己的策略"), session,
                SimpleNamespace(id=OWNER_ID),
            )
            assert response.name == "我自己的策略"
        await engine.dispose()

    asyncio.run(scenario())
