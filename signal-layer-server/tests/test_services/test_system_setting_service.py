import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.services.system_setting_service import (
    DEFAULT_DIVERGENCE_POWER_RATIO,
    get_divergence_power_ratio,
    set_divergence_power_ratio,
)


def test_divergence_ratio_defaults_and_persists():
    async def scenario():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            assert await get_divergence_power_ratio(session) == DEFAULT_DIVERGENCE_POWER_RATIO
            await set_divergence_power_ratio(session, 0.65)
        async with sessions() as session:
            assert await get_divergence_power_ratio(session) == 0.65
        await engine.dispose()

    asyncio.run(scenario())
