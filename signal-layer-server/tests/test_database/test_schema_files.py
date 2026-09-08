import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_sqlite_initialization_script_creates_fixed_tables():
    sql = (ROOT / "database/sqlite/001_app_schema.sql").read_text(encoding="utf-8")
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(sql)
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

    assert {"templates", "klines"}.issubset(tables)
    assert "trade_params" in template_columns


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
    assert "CREATE TABLE IF NOT EXISTS templates" in app_sql
    assert "CREATE TABLE IF NOT EXISTS klines" in app_sql
    assert "trade_params" in app_sql
    assert "CREATE TABLE IF NOT EXISTS stock_info" in market_sql
