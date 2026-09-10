"""将旧 SQLite 应用数据按业务编码迁移到 SIGNAL_MYSQL_* 配置的 MySQL。"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.market_data.mysql_store import MYSQL_CONFIG


def source_rows(connection: sqlite3.Connection, table: str) -> list[dict]:
    connection.row_factory = sqlite3.Row
    return [dict(row) for row in connection.execute(f"SELECT * FROM {table}")]


def upsert_by(cursor, table: str, row: dict, unique_key: str, *, skip: set[str] | None = None):
    values = {key: value for key, value in row.items() if key not in (skip or set())}
    columns = list(values)
    quoted = ",".join(f"`{column}`" for column in columns)
    placeholders = ",".join(["%s"] * len(columns))
    updates = ",".join(
        f"`{column}`=VALUES(`{column}`)" for column in columns if column != unique_key
    )
    cursor.execute(
        f"INSERT INTO `{table}` ({quoted}) VALUES ({placeholders}) "
        f"ON DUPLICATE KEY UPDATE {updates}",
        tuple(values[column] for column in columns),
    )


def id_map(cursor, table: str, key: str) -> dict[str, int]:
    cursor.execute(f"SELECT id, `{key}` FROM `{table}`")
    return {str(row[1]): int(row[0]) for row in cursor.fetchall()}


def migrate(source_path: Path):
    import pymysql

    source = sqlite3.connect(source_path)
    target = pymysql.connect(**MYSQL_CONFIG)
    counts: dict[str, int] = {}
    try:
        modules = source_rows(source, "modules")
        permissions = source_rows(source, "permissions")
        roles = source_rows(source, "roles")
        users = source_rows(source, "users")
        role_links = source_rows(source, "role_permissions")
        user_links = source_rows(source, "user_roles")
        templates = source_rows(source, "templates")

        source_module_codes = {row["id"]: row["code"] for row in modules}
        source_permission_codes = {row["id"]: row["code"] for row in permissions}
        source_role_codes = {row["id"]: row["code"] for row in roles}
        source_usernames = {row["id"]: row["username"] for row in users}

        with target.cursor() as cursor:
            for row in modules:
                upsert_by(cursor, "modules", row, "code", skip={"id"})
            mysql_modules = id_map(cursor, "modules", "code")

            for row in permissions:
                migrated = dict(row)
                module_code = source_module_codes.get(row["module_id"])
                migrated["module_id"] = mysql_modules.get(module_code) if module_code else None
                upsert_by(cursor, "permissions", migrated, "code", skip={"id"})
            mysql_permissions = id_map(cursor, "permissions", "code")

            for row in roles:
                upsert_by(cursor, "roles", row, "code", skip={"id"})
            mysql_roles = id_map(cursor, "roles", "code")

            for row in users:
                upsert_by(cursor, "users", row, "username", skip={"id"})
            mysql_users = id_map(cursor, "users", "username")

            for role_code in source_role_codes.values():
                cursor.execute("DELETE FROM role_permissions WHERE role_id=%s", (mysql_roles[role_code],))
            for link in role_links:
                role_code = source_role_codes[link["role_id"]]
                permission_code = source_permission_codes[link["permission_id"]]
                cursor.execute(
                    "INSERT IGNORE INTO role_permissions(role_id, permission_id) VALUES (%s, %s)",
                    (mysql_roles[role_code], mysql_permissions[permission_code]),
                )

            for username in source_usernames.values():
                cursor.execute("DELETE FROM user_roles WHERE user_id=%s", (mysql_users[username],))
            for link in user_links:
                username = source_usernames[link["user_id"]]
                role_code = source_role_codes[link["role_id"]]
                cursor.execute(
                    "INSERT IGNORE INTO user_roles(user_id, role_id) VALUES (%s, %s)",
                    (mysql_users[username], mysql_roles[role_code]),
                )

            for row in templates:
                migrated = dict(row)
                username = source_usernames.get(row["user_id"])
                migrated["user_id"] = mysql_users.get(username) if username else mysql_users.get("admin")
                upsert_by(cursor, "templates", migrated, "id")

        target.commit()
        counts = {
            "modules": len(modules), "permissions": len(permissions), "roles": len(roles),
            "users": len(users), "role_permissions": len(role_links),
            "user_roles": len(user_links), "templates": len(templates),
        }
    except Exception:
        target.rollback()
        raise
    finally:
        source.close()
        target.close()
    for table, count in counts.items():
        print(f"{table}: {count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="旧 SQLite 文件")
    args = parser.parse_args()
    migrate(args.source)
