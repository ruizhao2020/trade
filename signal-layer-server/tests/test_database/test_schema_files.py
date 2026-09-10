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
    finally:
        connection.close()

    assert {
        "templates", "klines", "users", "roles", "modules", "permissions",
        "user_roles", "role_permissions",
    }.issubset(tables)
    assert "trade_params" in template_columns
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(sql)
        module_columns = {row[1] for row in connection.execute("PRAGMA table_info(modules)")}
    finally:
        connection.close()
    assert "api_prefixes" in module_columns
    assert "api_permission" in module_columns


def test_sqlite_seed_creates_default_admin_roles_and_modules():
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript((ROOT / "database/sqlite/001_app_schema.sql").read_text(encoding="utf-8"))
        seed_sql = (ROOT / "database/sqlite/010_access_control_seed.sql").read_text(encoding="utf-8")
        connection.executescript(seed_sql)
        connection.executescript(seed_sql)
        assert connection.execute("SELECT COUNT(*) FROM modules").fetchone()[0] == 4
        assert connection.execute("SELECT COUNT(*) FROM permissions").fetchone()[0] == 14
        assert connection.execute("SELECT COUNT(*) FROM roles").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM users WHERE username='admin'").fetchone()[0] == 1
        admin_permissions = connection.execute(
            "SELECT COUNT(*) FROM role_permissions rp JOIN roles r ON r.id=rp.role_id WHERE r.code='admin'"
        ).fetchone()[0]
        assert admin_permissions == 14
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
    assert "CREATE TABLE IF NOT EXISTS stock_info" in market_sql
    assert "INSERT INTO users" in seed_sql
    assert "INSERT INTO roles" in seed_sql
    assert "INSERT INTO modules" in seed_sql
