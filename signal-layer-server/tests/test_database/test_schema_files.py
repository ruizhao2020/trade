import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_sqlite_initialization_script_creates_fixed_tables():
    sql = (ROOT / "database/sqlite/001_app_schema.sql").read_text(encoding="utf-8")
    seed_sql = (ROOT / "database/sqlite/010_access_control_seed.sql").read_text(encoding="utf-8")
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(sql)
        connection.executescript(seed_sql)
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        template_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(templates)")
        }
        kline_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(klines)")
        }
    finally:
        connection.close()

    assert {
        "templates", "klines", "users", "roles", "modules", "permissions",
        "user_roles", "role_permissions", "public_indicator_policies", "public_indicator_feature_policies",
        "content_templates", "article_drafts",
        "system_settings",
    }.issubset(tables)
    assert "trade_params" in template_columns
    assert {"amount", "turnover_rate", "circulating_shares", "adjustment_factor", "adjustment_type"}.issubset(kline_columns)
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(sql)
        module_columns = {row[1] for row in connection.execute("PRAGMA table_info(modules)")}
    finally:
        connection.close()
    assert "api_prefixes" in module_columns
    assert "api_permission" in module_columns
    assert "public_access" in module_columns


def test_both_dialect_schemas_carry_the_audit_status_column():
    """users.status 必须同时出现在 mysql 与 sqlite 建表脚本里。

    schema 不由 Alembic 管理，新列要手工落到两处 SQL 加 `_ensure_compat_columns`。
    漏掉任何一处：全新安装缺列（接口 500），或老库升级缺列（同样 500）。
    """
    for dialect in ("mysql", "sqlite"):
        sql = (ROOT / f"database/{dialect}/001_app_schema.sql").read_text(encoding="utf-8")
        connection = sqlite3.connect(":memory:")
        try:
            if dialect == "sqlite":
                connection.executescript(sql)
                columns = {row[1]: row for row in connection.execute("PRAGMA table_info(users)")}
                assert "status" in columns, "sqlite 建表脚本缺 users.status"
                # NOT NULL + DEFAULT 'active'：历史/存量行必须自动成为已通过
                assert columns["status"][3] == 1 and "active" in columns["status"][4].lower()
            else:
                assert "status" in sql and "VARCHAR(20)" in sql
        finally:
            connection.close()


def test_migration_promotes_existing_users_to_active():
    """老库升级：补列后历史账号必须是 active，否则升级会把所有人锁在门外。"""
    from sqlalchemy import create_engine, inspect, text

    from app.db import _ensure_compat_columns

    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        # 模拟升级前的 users 表：只有旧列，没有 status
        connection.execute(text(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(50) NOT NULL UNIQUE, "
            "password_hash VARCHAR(255) NOT NULL, display_name VARCHAR(80) NOT NULL DEFAULT '', "
            "enabled BOOLEAN NOT NULL DEFAULT 1)"
        ))
        connection.execute(text(
            "INSERT INTO users (id, username, password_hash, display_name, enabled) "
            "VALUES (1, 'admin', 'x', '系统管理员', 1)"
        ))
        _ensure_compat_columns(connection)

        assert "status" in {column["name"] for column in inspect(connection).get_columns("users")}
        assert connection.execute(text("SELECT status FROM users WHERE username='admin'")).scalar() == "active"


def test_sqlite_seed_creates_default_admin_roles_and_modules():
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript((ROOT / "database/sqlite/001_app_schema.sql").read_text(encoding="utf-8"))
        seed_sql = (ROOT / "database/sqlite/010_access_control_seed.sql").read_text(encoding="utf-8")
        connection.executescript(seed_sql)
        connection.executescript(seed_sql)
        # 断言"核心模块/权限存在 + 管理员拥有全部权限"，避免每新增一个模块就改数量
        module_codes = {row[0] for row in connection.execute("SELECT code FROM modules")}
        assert {"indicators", "strategy", "screener", "admin", "notifications", "content", "advisor"} <= module_codes
        permission_codes = {row[0] for row in connection.execute("SELECT code FROM permissions")}
        assert {"indicators.view", "strategy.view", "screener.view", "admin.view",
                "notifications.view", "content.view", "advisor.view", "advisor.run"} <= permission_codes
        assert connection.execute("SELECT COUNT(*) FROM roles").fetchone()[0] == 3
        assert connection.execute("SELECT COUNT(*) FROM users WHERE username='admin'").fetchone()[0] == 1
        assert connection.execute("SELECT public_access FROM modules WHERE code='indicators'").fetchone()[0] == 1
        assert connection.execute("SELECT registration_default FROM roles WHERE code='member'").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM public_indicator_policies").fetchone()[0] == 11
        assert connection.execute("SELECT public_visible FROM public_indicator_policies WHERE indicator_type='volume_structure'").fetchone()[0] == 0
        assert connection.execute("SELECT public_visible FROM public_indicator_policies WHERE indicator_type='dilun_structure'").fetchone()[0] == 0
        assert connection.execute("SELECT public_visible FROM public_indicator_feature_policies WHERE indicator_type='chan' AND feature_code='buy_sell_points'").fetchone()[0] == 0
        assert connection.execute("SELECT value_number FROM system_settings WHERE key='chan.divergence_power_ratio'").fetchone()[0] == 0.7
        admin_permissions = connection.execute(
            "SELECT COUNT(*) FROM role_permissions rp JOIN roles r ON r.id=rp.role_id WHERE r.code='admin'"
        ).fetchone()[0]
        assert admin_permissions == len(permission_codes), "管理员应当拥有全部权限"
    finally:
        connection.close()


def test_saved_schemas_exclude_runtime_dynamic_tables():
    schema_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "database").rglob("*.sql")
    )
    assert "_market_data_coverage" not in schema_text
    assert "_5分钟" not in schema_text


def test_mysql_schemas_contain_only_expected_fixed_tables():
    app_sql = (ROOT / "database/mysql/001_app_schema.sql").read_text(encoding="utf-8")
    market_sql = (ROOT / "database/mysql/002_market_reference_schema.sql").read_text(encoding="utf-8")
    seed_sql = (ROOT / "database/mysql/010_access_control_seed.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS templates" in app_sql
    assert "CREATE TABLE IF NOT EXISTS klines" in app_sql
    assert "trade_params" in app_sql
    assert "CREATE TABLE IF NOT EXISTS system_settings" in app_sql
    assert "CREATE TABLE IF NOT EXISTS stock_info" in market_sql
    assert "INSERT INTO users" in seed_sql
    assert "INSERT INTO roles" in seed_sql
    assert "INSERT INTO modules" in seed_sql
