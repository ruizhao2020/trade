from collections.abc import AsyncIterator

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.models.base import Base
from app.models.template import Template  # noqa: F401 — 确保模型注册到 Base.metadata
from app.config import settings

_engine = None
_session_factory = None


def _get_db_url() -> str:
    if settings.mysql_host == "localhost" and settings.mysql_database == "signal_layer":
        return "sqlite+aiosqlite:///./data/signal_layer.db"
    return settings.database_url


async def init_db():
    global _engine, _session_factory
    url = _get_db_url()
    _engine = create_async_engine(url, echo=False)
    _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_compat_columns)


def _ensure_compat_columns(connection):
    """为 create_all 无法更新的旧数据库补齐新增列。"""
    inspector = inspect(connection)
    if "templates" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("templates")}
    if "trade_params" not in columns:
        connection.execute(text("ALTER TABLE templates ADD COLUMN trade_params JSON"))


async def get_session() -> AsyncIterator[AsyncSession]:
    if _session_factory is None:
        await init_db()
    async with _session_factory() as session:
        yield session


async def close_db():
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None
