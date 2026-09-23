from collections.abc import AsyncIterator

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.models.base import Base
from app.models.template import Template  # noqa: F401 — 确保模型注册到 Base.metadata
from app.models.auth import Module, Permission, PublicIndicatorFeaturePolicy, PublicIndicatorPolicy, Role, User  # noqa: F401
from app.models.kline import Kline  # noqa: F401 — 注册固定 K 线模型
from app.models.notification import NotificationChannel, NotificationEvent, NotificationTemplate, ScreenerSchedule, StrategyMonitor  # noqa: F401
from app.models.content import ArticleDraft, ContentTemplate  # noqa: F401
from app.models.system_setting import SystemSetting  # noqa: F401
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
    table_names = set(inspector.get_table_names())
    if "public_chan_feature_policies" in table_names and "public_indicator_feature_policies" in table_names:
        if connection.dialect.name == "mysql":
            connection.execute(text(
                "INSERT IGNORE INTO public_indicator_feature_policies "
                "(indicator_type, feature_code, display_name, public_visible, show_details, sort_order, created_at, updated_at) "
                "SELECT 'chan', feature_code, display_name, public_visible, show_details, sort_order, created_at, updated_at "
                "FROM public_chan_feature_policies"
            ))
        else:
            connection.execute(text(
                "INSERT OR IGNORE INTO public_indicator_feature_policies "
                "(indicator_type, feature_code, display_name, public_visible, show_details, sort_order, created_at, updated_at) "
                "SELECT 'chan', feature_code, display_name, public_visible, show_details, sort_order, created_at, updated_at "
                "FROM public_chan_feature_policies"
            ))
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
        if "public_access" not in module_columns:
            connection.execute(text("ALTER TABLE modules ADD COLUMN public_access BOOLEAN NOT NULL DEFAULT 0"))
            connection.execute(text("UPDATE modules SET public_access = 1 WHERE code = 'indicators'"))
    if "roles" in inspector.get_table_names():
        role_columns = {column["name"] for column in inspector.get_columns("roles")}
        if "registration_default" not in role_columns:
            connection.execute(text("ALTER TABLE roles ADD COLUMN registration_default BOOLEAN NOT NULL DEFAULT 0"))
            # 该字段首次加入时，历史系统只有 member 作为注册角色；直接设为默认。
            # 后续管理员可在系统中切换为其他角色，迁移不会再次执行。
            connection.execute(text("UPDATE roles SET registration_default = 1 WHERE code = 'member'"))
    if "klines" in inspector.get_table_names():
        kline_columns = {column["name"] for column in inspector.get_columns("klines")}
        additions = {
            "amount": "DECIMAL(24,8) NULL",
            "turnover_rate": "DECIMAL(16,8) NULL",
            "circulating_shares": "DECIMAL(24,4) NULL",
            "adjustment_factor": "DECIMAL(24,12) NULL",
            "adjustment_type": "VARCHAR(8) NULL",
        }
        for column, definition in additions.items():
            if column not in kline_columns:
                connection.execute(text(f"ALTER TABLE klines ADD COLUMN {column} {definition}"))
    if "strategy_monitors" in inspector.get_table_names():
        monitor_columns = {column["name"] for column in inspector.get_columns("strategy_monitors")}
        monitor_additions = {
            "schedule_enabled": "BOOLEAN NOT NULL DEFAULT 0",
            "schedule_time": "VARCHAR(5) NOT NULL DEFAULT '09:30'",
            # Nullable keeps this migration compatible with older MySQL
            # versions that do not allow JSON defaults in ALTER TABLE.
            "schedule_weekdays": "JSON NULL",
            "last_schedule_key": "VARCHAR(32) NULL",
            "event_types": "JSON NULL",
        }
        for column, definition in monitor_additions.items():
            if column not in monitor_columns:
                connection.execute(text(f"ALTER TABLE strategy_monitors ADD COLUMN {column} {definition}"))
    if "notification_channels" in inspector.get_table_names():
        channel_columns = {column["name"] for column in inspector.get_columns("notification_channels")}
        if "is_shared" not in channel_columns:
            connection.execute(text("ALTER TABLE notification_channels ADD COLUMN is_shared BOOLEAN NOT NULL DEFAULT 0"))
    if "notification_events" in inspector.get_table_names() and connection.dialect.name == "mysql":
        # Scheduled screener results reuse the event table but do not have a
        # strategy monitor row. Remove the old FK left by the first version of
        # the notification schema; runtime models already treat these ids as
        # source identifiers rather than relational references.
        foreign_keys = inspect(connection).get_foreign_keys("notification_events")
        if any(item.get("name") == "fk_notification_event_monitor" for item in foreign_keys):
            connection.execute(text("ALTER TABLE notification_events DROP FOREIGN KEY fk_notification_event_monitor"))
    if "content_templates" in inspector.get_table_names():
        content_template_columns = {column["name"] for column in inspector.get_columns("content_templates")}
        if "user_id" not in content_template_columns:
            connection.execute(text("ALTER TABLE content_templates ADD COLUMN user_id INTEGER NULL"))


def _ensure_mysql_utf8mb4(connection):
    """只规范固定应用表字符集，不处理按标的/周期动态创建的行情表。"""
    if connection.dialect.name != "mysql":
        return
    fixed_tables = (
        "templates", "users", "roles", "modules", "permissions",
        "user_roles", "role_permissions", "klines", "public_indicator_policies", "public_indicator_feature_policies",
        "notification_channels", "notification_templates", "strategy_monitors", "notification_events", "screener_schedules",
        "content_templates", "article_drafts",
        "system_settings",
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
