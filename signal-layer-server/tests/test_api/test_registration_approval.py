"""注册审核门：注册 -> 待审核 -> 管理员通过/拒绝 的完整链路。

为什么必须走真实 ASGI 栈：这道门的三个关键分支分别落在
`authenticate`（登录）、`module_access` 中间件（私有模块）和 `current_user`
（/auth/me 这类不走模块前缀的路由）里。只测处理函数会漏掉中间件那一层，
而它恰好是"待审核账号拿不到私有数据"的唯一保证。

安全约定：拒绝原因只在密码正确之后才返回，否则报错文案本身就是账号状态探测器。
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.main import app
from app.middleware import module_access
from app.models.auth import USER_STATUS_PENDING, User
from app.db import get_session
from app.services.auth_service import create_access_token
from app.services.module_access_service import invalidate_module_rules

SERVER_ROOT = Path(__file__).resolve().parents[2]
VALID_PASSWORD = "Probe12345!"


@pytest.fixture
def seeded_db():
    """临时 SQLite 文件 + database/sqlite 下真实的建表与种子脚本。"""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "approval.db"
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
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": raw_headers,
        "client": ("127.0.0.1", 41234),
        "server": ("testserver", 80),
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


async def _user(path: Path, username: str) -> User:
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            return (await session.execute(select(User).where(User.username == username))).scalar_one()
    finally:
        await engine.dispose()


async def _admin_id(path: Path) -> int:
    return (await _user(path, "admin")).id


async def _create_active_user(path: Path, username: str, permission_codes: list[str]) -> int:
    """直接建一个已通过审核、只持有指定权限的用户（用于隔离权限分支）。"""
    from app.models.auth import Permission, Role, role_permissions, user_roles
    from app.services.auth_service import hash_password

    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            role = Role(code=f"role_{username}", name=username, built_in=False, enabled=True)
            session.add(role)
            await session.flush()
            permissions = (await session.execute(
                select(Permission).where(Permission.code.in_(permission_codes))
            )).scalars().all()
            assert len(permissions) == len(permission_codes), "权限码不存在"
            await session.execute(role_permissions.insert(), [
                {"role_id": role.id, "permission_id": item.id} for item in permissions
            ])
            user = User(
                username=username, display_name=username,
                password_hash=hash_password(VALID_PASSWORD), enabled=True,
            )
            session.add(user)
            await session.flush()
            await session.execute(user_roles.insert().values(user_id=user.id, role_id=role.id))
            await session.commit()
            return user.id
    finally:
        await engine.dispose()


def _bearer(user_id: int) -> dict:
    token, _ = create_access_token(user_id)
    return {"Authorization": f"Bearer {token}"}


async def _register(username: str) -> tuple[int, dict]:
    return await _asgi_request(
        "POST", "/api/v1/auth/register",
        body={"username": username, "password": VALID_PASSWORD, "display_name": "待审用户"},
    )


# ── 注册：不再直接发令牌 ────────────────────────────────────────────────

def test_register_returns_pending_without_token(seeded_db):
    async def run():
        """注册接口不得下发令牌，账号落库为待审核。"""
        cleanup = _bind_session(seeded_db)
        try:
            status, body = await _register("pending_user")
            assert status == 201
            assert "access_token" not in body
            assert body["status"] == USER_STATUS_PENDING
            assert body["username"] == "pending_user"

            user = await _user(seeded_db, "pending_user")
            assert user.status == USER_STATUS_PENDING
            assert user.enabled is True  # enabled 与审核状态正交：注册不涉及"停用"
        finally:
            await cleanup()
    asyncio.run(run())



def test_duplicate_registration_is_rejected(seeded_db):
    async def run():
        cleanup = _bind_session(seeded_db)
        try:
            assert (await _register("dup_user"))[0] == 201
            status, body = await _register("dup_user")
            assert status == 409
            assert "已存在" in body["detail"]
        finally:
            await cleanup()
    asyncio.run(run())



# ── 待审核账号：登录与私有模块全部被挡 ─────────────────────────────────

def test_pending_account_cannot_login(seeded_db):
    async def run():
        """待审核账号登录时给出明确原因，而不是笼统的"用户名或密码错误"。"""
        cleanup = _bind_session(seeded_db)
        try:
            await _register("pending_login")
            status, body = await _asgi_request(
                "POST", "/api/v1/auth/login", body={"username": "pending_login", "password": VALID_PASSWORD}
            )
            assert status == 401
            assert "审核中" in body["detail"]
        finally:
            await cleanup()
    asyncio.run(run())



def test_wrong_password_does_not_leak_audit_status(seeded_db):
    async def run():
        """密码错误时必须仍是通用文案——否则文案成了账号状态探测器。"""
        cleanup = _bind_session(seeded_db)
        try:
            await _register("pending_secret")
            status, body = await _asgi_request(
                "POST", "/api/v1/auth/login", body={"username": "pending_secret", "password": "WrongPass123!"}
            )
            assert status == 401
            assert body["detail"] == "用户名或密码错误"
        finally:
            await cleanup()
    asyncio.run(run())



def test_pending_account_token_is_blocked_on_private_modules(seeded_db):
    async def run():
        """即便手握合法令牌，待审核账号也进不了私有模块（中间件拦截）。"""
        cleanup = _bind_session(seeded_db)
        try:
            await _register("pending_module")
            user = await _user(seeded_db, "pending_module")
            status, body = await _asgi_request("GET", "/api/v1/templates", headers=_bearer(user.id))
            assert status == 401
            assert "审核中" in body["detail"]
        finally:
            await cleanup()
    asyncio.run(run())



def test_pending_account_token_is_blocked_on_me(seeded_db):
    async def run():
        """不走模块前缀的 /auth/me 也必须拦住（current_user 分支）。"""
        cleanup = _bind_session(seeded_db)
        try:
            await _register("pending_me")
            user = await _user(seeded_db, "pending_me")
            status, body = await _asgi_request("GET", "/api/v1/auth/me", headers=_bearer(user.id))
            assert status == 401
            assert "审核中" in body["detail"]
        finally:
            await cleanup()
    asyncio.run(run())



# ── 管理员审核 ──────────────────────────────────────────────────────────

async def _approve(admin_id: int, user_id: int, role_codes: list[str] | None = None):
    return await _asgi_request(
        "POST", f"/api/v1/admin/users/{user_id}/approve",
        headers=_bearer(admin_id), body={"role_codes": role_codes} if role_codes else {},
    )


def test_approve_unlocks_login_and_private_modules(seeded_db):
    async def run():
        """通过后：能登录，且授予含 private.access 的角色即可使用私有能力。"""
        cleanup = _bind_session(seeded_db)
        try:
            await _register("approved_user")
            admin_id = await _admin_id(seeded_db)
            target = await _user(seeded_db, "approved_user")

            status, body = await _approve(admin_id, target.id, ["researcher"])
            assert status == 200
            assert body["status"] == "active"
            assert body["role_codes"] == ["researcher"]

            status, body = await _asgi_request(
                "POST", "/api/v1/auth/login", body={"username": "approved_user", "password": VALID_PASSWORD}
            )
            assert status == 200
            assert body["access_token"]
            # 私有模块出现在导航里
            assert "strategy" in [module["code"] for module in body["user"]["modules"]]

            token = body["access_token"]
            status, _ = await _asgi_request("GET", "/api/v1/templates", headers={"Authorization": f"Bearer {token}"})
            assert status != 401
        finally:
            await cleanup()
    asyncio.run(run())



def test_approve_without_roles_keeps_registration_default(seeded_db):
    async def run():
        """不指定角色时保留注册时分配的默认角色（不静默提权）。"""
        cleanup = _bind_session(seeded_db)
        try:
            await _register("kept_role")
            admin_id = await _admin_id(seeded_db)
            target = await _user(seeded_db, "kept_role")
            registered_roles = sorted(role.code for role in target.roles)

            status, body = await _approve(admin_id, target.id)
            assert status == 200
            assert sorted(body["role_codes"]) == registered_roles
            assert body["status"] == "active"
        finally:
            await cleanup()
    asyncio.run(run())



def test_rejected_account_cannot_login(seeded_db):
    async def run():
        cleanup = _bind_session(seeded_db)
        try:
            await _register("rejected_user")
            admin_id = await _admin_id(seeded_db)
            target = await _user(seeded_db, "rejected_user")

            status, body = await _asgi_request(
                "POST", f"/api/v1/admin/users/{target.id}/reject", headers=_bearer(admin_id), body={}
            )
            assert status == 200
            assert body["status"] == "rejected"

            status, body = await _asgi_request(
                "POST", "/api/v1/auth/login", body={"username": "rejected_user", "password": VALID_PASSWORD}
            )
            assert status == 401
            assert "审核未通过" in body["detail"]
        finally:
            await cleanup()
    asyncio.run(run())



def test_rejected_account_can_be_approved_afterwards(seeded_db):
    async def run():
        """拒绝是状态而不是删除：管理员改主意后可以放行。"""
        cleanup = _bind_session(seeded_db)
        try:
            await _register("second_chance")
            admin_id = await _admin_id(seeded_db)
            target = await _user(seeded_db, "second_chance")
            await _asgi_request("POST", f"/api/v1/admin/users/{target.id}/reject", headers=_bearer(admin_id), body={})

            status, body = await _approve(admin_id, target.id)
            assert status == 200
            assert body["status"] == "active"
            status, _ = await _asgi_request(
                "POST", "/api/v1/auth/login", body={"username": "second_chance", "password": VALID_PASSWORD}
            )
            assert status == 200
        finally:
            await cleanup()
    asyncio.run(run())



def test_admin_list_exposes_status_and_creation_time(seeded_db):
    async def run():
        """管理员列表必须能看到审核状态，否则无从知道有人在等。"""
        cleanup = _bind_session(seeded_db)
        try:
            await _register("listed_user")
            admin_id = await _admin_id(seeded_db)
            status, users = await _asgi_request("GET", "/api/v1/admin/users", headers=_bearer(admin_id))
            assert status == 200
            listed = next(item for item in users if item["username"] == "listed_user")
            assert listed["status"] == USER_STATUS_PENDING
            assert listed["created_at"]
            # 管理员自己仍是已通过，升级不会锁住现有账号
            assert next(item for item in users if item["username"] == "admin")["status"] == "active"
        finally:
            await cleanup()
    asyncio.run(run())



# ── 审核接口的权限边界 ──────────────────────────────────────────────────

def test_pending_account_cannot_approve_itself(seeded_db):
    async def run():
        """待审核账号持有令牌也不能自己给自己放行。"""
        cleanup = _bind_session(seeded_db)
        try:
            await _register("self_approve")
            target = await _user(seeded_db, "self_approve")
            status, _ = await _approve(target.id, target.id)
            assert status in (401, 403)  # 先被中间件/权限挡住
            # 状态未被改动
            assert (await _user(seeded_db, "self_approve")).status == USER_STATUS_PENDING
        finally:
            await cleanup()
    asyncio.run(run())



def test_admin_cannot_audit_itself(seeded_db):
    async def run():
        cleanup = _bind_session(seeded_db)
        try:
            admin_id = await _admin_id(seeded_db)
            status, body = await _asgi_request(
                "POST", f"/api/v1/admin/users/{admin_id}/reject", headers=_bearer(admin_id), body={}
            )
            assert status == 400
            assert "不能审核自己" in body["detail"]
            assert (await _user(seeded_db, "admin")).status == "active"
        finally:
            await cleanup()
    asyncio.run(run())



def test_review_requires_admin_users_permission(seeded_db):
    async def run():
        """已通过审核但缺少 admin.users 的账号不能审核别人。

        构造 private.access + admin.view 但**不含** admin.users：
        这样模块准入（admin 模块要求 admin.view）会放行，唯一拦住它的
        只能是路由上那个 require_permission("admin.users")——也就是纵深防御的
        第二层。用现成角色测不到这一层：缺 admin.view 的角色会被中间件先行挡下。
        """
        cleanup = _bind_session(seeded_db)
        try:
            await _register("target_of_auditor")
            target = await _user(seeded_db, "target_of_auditor")
            reviewer_id = await _create_active_user(
                seeded_db, "auditor", ["private.access", "admin.view"]
            )

            status, body = await _approve(reviewer_id, target.id)
            assert status == 403
            assert "admin.users" in body["detail"]
            assert (await _user(seeded_db, "target_of_auditor")).status == USER_STATUS_PENDING
        finally:
            await cleanup()

    asyncio.run(run())
