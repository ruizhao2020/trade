from collections.abc import AsyncIterator

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.models.base import Base
from app.models.template import Template  # noqa: F401 — 确保模型注册到 Base.metadata
from app.models.auth import Module, Permission, Role, User  # noqa: F401
from app.config import settings

_engine = None
_session_factory = None


def _get_db_url() -> str:
    """应用运行时统一使用配置的 MySQL；SQLite 仅用于测试和历史迁移。"""
    return settings.database_url


async def init_db():
    global _engine, _session_factory
    url = _get_db_url()
    _engine = create_async_engine(
        url,
        echo=False,
        pool_pre_ping=True,
        pool_size=settings.mysql_pool_size,
        max_overflow=settings.mysql_max_overflow,
    )
    _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_compat_columns)
        await conn.run_sync(_ensure_mysql_utf8mb4)

    await _seed_access_control()


def _ensure_compat_columns(connection):
    """为 create_all 无法更新的旧数据库补齐新增列。"""
    inspector = inspect(connection)
    if "templates" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("templates")}
    if "trade_params" not in columns:
        connection.execute(text("ALTER TABLE templates ADD COLUMN trade_params JSON"))
    if "modules" in inspector.get_table_names():
        module_columns = {column["name"] for column in inspector.get_columns("modules")}
        if "api_prefixes" not in module_columns:
            connection.execute(text("ALTER TABLE modules ADD COLUMN api_prefixes VARCHAR(500) NOT NULL DEFAULT ''"))
        if "api_permission" not in module_columns:
            connection.execute(text("ALTER TABLE modules ADD COLUMN api_permission VARCHAR(100) NOT NULL DEFAULT ''"))


def _ensure_mysql_utf8mb4(connection):
    """只规范固定应用表字符集，不处理按标的/周期动态创建的行情表。"""
    if connection.dialect.name != "mysql":
        return
    fixed_tables = (
        "templates", "users", "roles", "modules", "permissions",
        "user_roles", "role_permissions", "klines",
    )
    inspector = inspect(connection)
    existing = set(inspector.get_table_names())
    collations = dict(connection.execute(text(
        "SELECT table_name, table_collation FROM information_schema.tables "
        "WHERE table_schema=DATABASE()"
    )).fetchall())
    for table_name in fixed_tables:
        if table_name in existing and not str(collations.get(table_name, "")).lower().startswith("utf8mb4"):
            connection.execute(text(
                f"ALTER TABLE `{table_name}` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            ))


async def _seed_access_control():
    from app.services.auth_service import seed_access_control
    async with _session_factory() as session:
        await seed_access_control(session)


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
