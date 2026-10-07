"""管理员删除账号。

与「停用」的区别：停用保留账号和数据、可随时恢复；删除不可撤销，
并且要连带清掉该用户的私有数据——那些表在查询侧一律按 user_id 过滤，
账号没了它们既无人可见也无法被引用，留着只是孤儿行。

删除的两条硬边界：不能删自己、不能删最后一个管理员（否则系统锁死）。
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import get_session
from app.main import app
from app.middleware import module_access
from app.models.auth import User
from app.services.auth_service import create_access_token
from app.services.module_access_service import invalidate_module_rules

SERVER_ROOT = Path(__file__).resolve().parents[2]
VALID_PASSWORD = "Probe12345!"


@pytest.fixture
def seeded_db():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "deletion.db"
        connection = sqlite3.connect(path)
        try:
            connection.executescript((SERVER_ROOT / "database/sqlite/001_app_schema.sql").read_text(encoding="utf-8"))
            connection.executescript((SERVER_ROOT / "database/sqlite/010_access_control_seed.sql").read_text(encoding="utf-8"))
            connection.commit()
        finally:
            connection.close()
        yield path


async def _asgi_request(method: str, path: str, *, headers: dict | None = None, body: dict | None = None):
    payload = json.dumps(body).encode("utf-8") if body is not None else b""
    raw_headers = [(key.lower().encode(), value.encode()) for key, value in (headers or {}).items()]
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
        "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": b"",
        "root_path": "", "headers": raw_headers, "client": ("127.0.0.1", 41234), "server": ("testserver", 80),
    }
    messages: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}

    async def send(message):
        messages.append(message)

    await app(scope, receive, send)
    status = next(item["status"] for item in messages if item["type"] == "http.response.start")
    raw = b"".join(item.get("body", b"") for item in messages if item["type"] == "http.response.body")
    try:
        parsed = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        parsed = raw.decode("utf-8", errors="replace")
    return status, parsed


def _bind_session(path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    module_access.get_session = override_get_session
    invalidate_module_rules()

    async def cleanup():
        app.dependency_overrides.pop(get_session, None)
        await engine.dispose()

    return cleanup


async def _scalar(path: Path, sql: str, params: dict | None = None):
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    try:
        async with engine.connect() as connection:
            return (await connection.execute(text(sql), params or {})).scalar()
    finally:
        await engine.dispose()


async def _all(path: Path, sql: str, params: dict | None = None):
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    try:
        async with engine.connect() as connection:
            return [tuple(row) for row in (await connection.execute(text(sql), params or {})).fetchall()]
    finally:
        await engine.dispose()


async def _user_id(path: Path, username: str) -> int | None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            user = (await session.execute(select(User).where(User.username == username))).scalar_one_or_none()
            return user.id if user else None
    finally:
        await engine.dispose()


def _bearer(user_id: int) -> dict:
    token, _ = create_access_token(user_id)
    return {"Authorization": f"Bearer {token}"}


async def _register(username: str) -> int:
    status, _ = await _asgi_request(
        "POST", "/api/v1/auth/register",
        body={"username": username, "password": VALID_PASSWORD, "display_name": username},
    )
    assert status == 201
    return 0


async def _seed_private_data(path: Path, user_id: int) -> None:
    """给用户塞满各类私有数据，验证删除时会被一并清理。"""
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    try:
        async with engine.begin() as connection:
            await connection.execute(text(
                "INSERT INTO templates (id, user_id, name, logic, condition_groups, primary_tf, enabled) "
                "VALUES ('tpl_probe', :uid, '探针策略', 'AND', '[]', '1d', 1)"
            ), {"uid": user_id})
            await connection.execute(text(
                "INSERT INTO notification_channels (user_id, name, channel_type, enabled, is_shared) "
                "VALUES (:uid, '探针渠道', 'browser', 1, 0)"
            ), {"uid": user_id})
            await connection.execute(text(
                "INSERT INTO strategy_monitors (user_id, template_id, symbol, symbol_name, channel_ids, enabled) "
                "VALUES (:uid, 'tpl_probe', '000001_sz', '平安银行', '[1]', 1)"
            ), {"uid": user_id})
            await connection.execute(text(
                "INSERT INTO article_drafts (user_id, template_id, title, symbol, symbol_name, market, as_of, "
                "timeframes, structured_data, chart_specs, standard_markdown, platform_variants, status) "
                "VALUES (:uid, 'tpl_probe', '探针草稿', '000001_sz', '平安银行', 'stock', '2026-01-01', "
                "'[]', '{}', '{}', '正文', '{}', 'draft')"
            ), {"uid": user_id})
    finally:
        await engine.dispose()


# ── 基本删除 ────────────────────────────────────────────────────────────

def test_delete_removes_account_and_private_data(seeded_db):
    async def run():
        cleanup = _bind_session(seeded_db)
        try:
            await _register("victim")
            victim_id = await _user_id(seeded_db, "victim")
            await _seed_private_data(seeded_db, victim_id)
            admin_id = await _user_id(seeded_db, "admin")

            status, body = await _asgi_request("DELETE", f"/api/v1/admin/users/{victim_id}", headers=_bearer(admin_id))
            assert status == 204, body

            assert await _user_id(seeded_db, "victim") is None
            # 私有数据一并清掉，不留孤儿
            assert await _all(seeded_db, "SELECT id FROM templates WHERE user_id = :u", {"u": victim_id}) == []
            assert await _all(seeded_db, "SELECT id FROM notification_channels WHERE user_id = :u", {"u": victim_id}) == []
            assert await _all(seeded_db, "SELECT id FROM strategy_monitors WHERE user_id = :u", {"u": victim_id}) == []
            assert await _all(seeded_db, "SELECT id FROM article_drafts WHERE user_id = :u", {"u": victim_id}) == []
            # 角色关联也清掉
            assert await _all(seeded_db, "SELECT user_id FROM user_roles WHERE user_id = :u", {"u": victim_id}) == []
        finally:
            await cleanup()

    asyncio.run(run())


def test_deleted_user_token_stops_working(seeded_db):
    """删除后遗留令牌立即失效（鉴权每次回库查用户）。"""
    async def run():
        cleanup = _bind_session(seeded_db)
        try:
            await _register("ghost")
            ghost_id = await _user_id(seeded_db, "ghost")
            ghost_token = _bearer(ghost_id)
            admin_id = await _user_id(seeded_db, "admin")

            await _asgi_request("DELETE", f"/api/v1/admin/users/{ghost_id}", headers=_bearer(admin_id))

            status, _ = await _asgi_request("GET", "/api/v1/auth/me", headers=ghost_token)
            assert status == 401
        finally:
            await cleanup()

    asyncio.run(run())


def test_pending_account_can_be_deleted(seeded_db):
    """待审核账号可以直接删掉（拒绝垃圾注册的常用路径）。"""
    async def run():
        cleanup = _bind_session(seeded_db)
        try:
            await _register("spam")
            spam_id = await _user_id(seeded_db, "spam")
            admin_id = await _user_id(seeded_db, "admin")

            status, _ = await _asgi_request("DELETE", f"/api/v1/admin/users/{spam_id}", headers=_bearer(admin_id))
            assert status == 204
            assert await _user_id(seeded_db, "spam") is None
        finally:
            await cleanup()

    asyncio.run(run())


def test_deleting_unknown_user_is_404(seeded_db):
    async def run():
        cleanup = _bind_session(seeded_db)
        try:
            admin_id = await _user_id(seeded_db, "admin")
            status, body = await _asgi_request("DELETE", "/api/v1/admin/users/9999", headers=_bearer(admin_id))
            assert status == 404
            assert "不存在" in body["detail"]
        finally:
            await cleanup()

    asyncio.run(run())


# ── 边界：不能把自己管理没了 ────────────────────────────────────────────

def test_cannot_delete_self(seeded_db):
    async def run():
        cleanup = _bind_session(seeded_db)
        try:
            admin_id = await _user_id(seeded_db, "admin")
            status, body = await _asgi_request("DELETE", f"/api/v1/admin/users/{admin_id}", headers=_bearer(admin_id))
            assert status == 400
            assert "不能删除自己" in body["detail"]
            assert await _user_id(seeded_db, "admin") is not None
        finally:
            await cleanup()

    asyncio.run(run())


def test_cannot_delete_the_last_admin(seeded_db):
    """删掉系统里最后一个管理员会让所有人都进不了用户管理，必须拦住。"""
    async def run():
        cleanup = _bind_session(seeded_db)
        try:
            admin_id = await _user_id(seeded_db, "admin")
            second_id = await _create_admin(seeded_db, "second_admin")

            # 还有两个管理员时，删掉种子 admin 是允许的
            status, _ = await _asgi_request("DELETE", f"/api/v1/admin/users/{admin_id}", headers=_bearer(second_id))
            assert status == 204

            # 造一个"有 admin.users 但不是管理员"的执行者：
            # 这样才会走到最后管理员守卫，而不是被自己的账号守卫或中间件挡住。
            await _create_active_user(seeded_db, "operator", ["private.access", "admin.view", "admin.users"])
            operator_id = await _user_id(seeded_db, "operator")

            status, body = await _asgi_request("DELETE", f"/api/v1/admin/users/{second_id}", headers=_bearer(operator_id))
            assert status == 400
            assert "最后一个管理员" in body["detail"]
            assert await _user_id(seeded_db, "second_admin") is not None, "守卫失败时不应真的删掉"
        finally:
            await cleanup()

    asyncio.run(run())


async def _create_admin(path: Path, username: str) -> int:
    """建一个已通过审核、持有 admin 角色的用户。"""
    return await _create_active_user(path, username, None, role_code="admin")


async def _create_active_user(
    path: Path, username: str, permission_codes: list[str] | None, *, role_code: str | None = None
) -> int:
    from app.models.auth import USER_STATUS_ACTIVE, Permission, Role, role_permissions, user_roles
    from app.services.auth_service import hash_password

    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            if role_code:
                role = (await session.execute(select(Role).where(Role.code == role_code))).scalar_one()
            else:
                role = Role(code=f"role_{username}", name=username, built_in=False, enabled=True)
                session.add(role)
                await session.flush()
                permissions = (await session.execute(
                    select(Permission).where(Permission.code.in_(permission_codes or []))
                )).scalars().all()
                assert len(permissions) == len(permission_codes or []), "权限码不存在"
                await session.execute(role_permissions.insert(), [
                    {"role_id": role.id, "permission_id": item.id} for item in permissions
                ])
            user = User(
                username=username, display_name=username,
                password_hash=hash_password(VALID_PASSWORD), enabled=True, status=USER_STATUS_ACTIVE,
            )
            session.add(user)
            await session.flush()
            await session.execute(user_roles.insert().values(user_id=user.id, role_id=role.id))
            await session.commit()
            return user.id
    finally:
        await engine.dispose()


# ── 权限边界 ────────────────────────────────────────────────────────────

def test_delete_requires_admin_users_permission(seeded_db):
    async def run():
        cleanup = _bind_session(seeded_db)
        try:
            await _register("victim2")
            victim_id = await _user_id(seeded_db, "victim2")
            await _register("intruder")
            intruder_id = await _user_id(seeded_db, "intruder")

            status, _ = await _asgi_request("DELETE", f"/api/v1/admin/users/{victim_id}", headers=_bearer(intruder_id))
            assert status in (401, 403)
            assert await _user_id(seeded_db, "victim2") is not None, "被拒时不应删除任何东西"
        finally:
            await cleanup()

    asyncio.run(run())
