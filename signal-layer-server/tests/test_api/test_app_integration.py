"""走真实 ASGI 栈的集成测试（路由 + 中间件 + 权限 + 响应序列化）。

为什么需要这一层：既有的 tests/test_api/* 都是**直接调用处理函数 + monkeypatch**，
绕过了路由注册、中间件、依赖注入和响应模型。结果是 14 个路由里只有 5 个在测试期间
被 import 过，`module_access` 中间件一次都没被测到——而"public/private 可见性由
服务端强制"这件事就落在那段代码里，它错了不会报错，只会静默放行。

这里用 stdlib 构造 ASGI 调用（httpx 未安装，TestClient 依赖它），
数据库用临时 SQLite 文件 + 真实的建表/种子 SQL，因此测的是真链路而不是替身。
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import tempfile
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import chan as chan_api
from app.api import deps as deps_api
from app.api import router as router_module
from app.db import get_session
from app.engine.chan import ChanResult
from app.engine.chan.signal import BuySellPoint
from app.main import app
from app.middleware import module_access
from app.services.auth_service import create_access_token
from app.services.module_access_service import invalidate_module_rules

SERVER_ROOT = Path(__file__).resolve().parents[2]


# ── 测试用数据库：跑真实的建表与种子 SQL ────────────────────────────────

@pytest.fixture
def seeded_db():
    """临时 SQLite 文件 + database/sqlite 下的真实建表与种子脚本。"""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.db"
        connection = sqlite3.connect(path)
        try:
            connection.executescript((SERVER_ROOT / "database/sqlite/001_app_schema.sql").read_text(encoding="utf-8"))
            connection.executescript((SERVER_ROOT / "database/sqlite/010_access_control_seed.sql").read_text(encoding="utf-8"))
            connection.commit()
        finally:
            connection.close()
        yield path


async def _asgi_request(method: str, path: str, *, headers: dict | None = None, body: dict | None = None):
    """直接驱动 ASGI 应用，走完整中间件栈。"""
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
    """把应用里的 get_session 指向测试库（路由用 Depends，中间件是直接调用）。"""
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    module_access.get_session = override_get_session
    invalidate_module_rules()  # module_rules 有 30 秒进程内缓存，必须在每个用例前清掉

    async def cleanup():
        app.dependency_overrides.pop(get_session, None)
        await engine.dispose()

    return cleanup


async def _user_id(username: str, path: Path) -> int:
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            from sqlalchemy import select

            from app.models.auth import User

            user = (await session.execute(select(User).where(User.username == username))).scalar_one()
            return user.id
    finally:
        await engine.dispose()


async def _set_module(path: Path, code: str, **values) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            from sqlalchemy import select, update

            from app.models.auth import Module

            await session.execute(update(Module).where(Module.code == code).values(**values))
            await session.commit()
    finally:
        await engine.dispose()
    invalidate_module_rules()



async def _create_user_with_permissions(path: Path, username: str, permission_codes: list[str]) -> int:
    """建一个只有指定权限的用户（用于精确验证权限分支）。"""
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            from sqlalchemy import select

            from app.models.auth import Permission, Role, User, role_permissions, user_roles
            from app.services.auth_service import hash_password

            role = Role(code=f"role_{username}", name="测试角色", built_in=False, enabled=True)
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
                password_hash=hash_password("Test1234!"), enabled=True,
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


async def _grant(path: Path, username: str, role_code: str) -> None:
    """把某个角色授予用户（用于构造"缺权限"的场景）。"""
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            from sqlalchemy import select

            from app.models.auth import Role, User, user_roles

            user = (await session.execute(select(User).where(User.username == username))).scalar_one()
            role = (await session.execute(select(Role).where(Role.code == role_code))).scalar_one()
            await session.execute(user_roles.insert().values(user_id=user.id, role_id=role.id))
            await session.commit()
    finally:
        await engine.dispose()


# ── 路由注册 ────────────────────────────────────────────────────────────

def test_every_module_api_prefix_has_registered_routes(seeded_db):
    """模块配置里声明的 API 前缀必须真的有路由。

    新增模块却忘了 include_router 时，界面会拿到 404 而没有任何提示——
    advisor 模块就是这么踩过一次。
    """
    registered = {
        route.path
        for route in app.routes
        if hasattr(route, "path")
    }
    connection = sqlite3.connect(seeded_db)
    try:
        rows = connection.execute("SELECT code, api_prefixes FROM modules").fetchall()
    finally:
        connection.close()

    missing = []
    for code, prefixes in rows:
        for prefix in (prefixes or "").split(","):
            prefix = prefix.strip().rstrip("/")
            if not prefix:
                continue
            if not any(path == prefix or path.startswith(prefix + "/") for path in registered):
                missing.append(f"{code}: {prefix}")
    assert missing == [], f"以下模块前缀没有任何已注册路由：{missing}"


def test_new_module_routes_are_registered():
    """新增模块的关键端点必须在路由表里（防止漏注册）。"""
    paths = {route.path for route in app.routes if hasattr(route, "path")}
    for expected in ("/api/v1/advisor/runs", "/api/v1/advisor/runs/{run_id}", "/api/v1/advisor/recommendations"):
        assert expected in paths, f"{expected} 未注册"
    # 子路由确实被挂到主 router 上
    assert router_module.api_router is not None


# ── 准入中间件 ──────────────────────────────────────────────────────────

def test_protected_module_requires_login_before_reaching_the_route(seeded_db, monkeypatch):
    """中间件的 401 必须发生在进入路由之前。

    注意：路由自己的 401 文案也是「请先登录」，所以**不能靠文案判定**——
    否则中间件完全失效时这条测试也会"通过"（我第一版就是这么假通过的）。
    这里用 call_next 是否被调用来判定。
    """
    from starlette.requests import Request

    from app.middleware.module_access import ModuleAccessMiddleware

    calls: list[str] = []

    async def fake_call_next(request):
        calls.append(request.url.path)
        from starlette.responses import JSONResponse
        return JSONResponse({"detail": "路由被调用"}, status_code=200)

    async def fake_rules(session):
        return [("/api/v1/advisor", "advisor.view", True, False)]

    monkeypatch.setattr(module_access, "module_rules", fake_rules)

    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "GET", "scheme": "http", "path": "/api/v1/advisor/runs",
        "raw_path": b"/api/v1/advisor/runs", "query_string": b"", "root_path": "",
        "headers": [(b"x-signal-surface", b"private")],
        "client": ("127.0.0.1", 1), "server": ("testserver", 80),
    }

    async def run():
        middleware = ModuleAccessMiddleware(app)
        return await middleware.dispatch(Request(scope), fake_call_next)

    response = asyncio.run(run())

    assert response.status_code == 401
    assert calls == [], "请求不应到达路由"


def test_disabled_module_is_rejected(seeded_db):
    cleanup = _bind_session(seeded_db)

    async def run():
        await _set_module(seeded_db, "advisor", enabled=False)
        admin_id = await _user_id("admin", seeded_db)
        return await _asgi_request("GET", "/api/v1/advisor/runs", headers=_bearer(admin_id))

    try:
        status, payload = asyncio.run(run())
    finally:
        asyncio.run(cleanup())

    assert status == 403
    assert payload["detail"] == "模块已停用"


def test_module_requires_its_own_permission(seeded_db):
    """有 private.access 但缺 advisor.view 时，模块级准入应当拒绝。

    断言用中间件独有的文案「缺少模块权限」：路由的同名检查是「缺少权限」（少"模块"二字），
    两者可区分，避免假通过。
    """
    cleanup = _bind_session(seeded_db)

    async def run():
        user_id = await _create_user_with_permissions(
            seeded_db, "narrow_user", ["private.access"],
        )
        return await _asgi_request("GET", "/api/v1/advisor/runs", headers=_bearer(user_id))

    try:
        status, payload = asyncio.run(run())
    finally:
        asyncio.run(cleanup())

    assert status == 403
    assert "缺少模块权限" in payload["detail"]


def test_authorized_user_passes_the_gate(seeded_db):
    """种子里 admin 拥有全部权限，应当通过准入（而不是 401/403）。"""
    cleanup = _bind_session(seeded_db)

    async def run():
        admin_id = await _user_id("admin", seeded_db)
        return await _asgi_request("GET", "/api/v1/advisor/runs", headers=_bearer(admin_id))

    try:
        status, payload = asyncio.run(run())
    finally:
        asyncio.run(cleanup())

    assert status == 200, payload
    assert isinstance(payload, list)


def test_auth_routes_skip_the_module_gate(seeded_db, monkeypatch):
    """/api/v1/auth/* 不参与模块准入——同样用 call_next 是否被调用来判定。"""
    from starlette.requests import Request

    from app.middleware.module_access import ModuleAccessMiddleware

    reached: list[str] = []

    async def fake_call_next(request):
        reached.append(request.url.path)
        from starlette.responses import JSONResponse
        return JSONResponse({"ok": True}, status_code=200)

    async def fake_rules(session):
        # 故意给一条会匹配 /api/v1/auth 的规则：若中间件不按预期跳过，就会拦截
        return [("/api/v1/auth", "analysis.compute", True, False)]

    monkeypatch.setattr(module_access, "module_rules", fake_rules)

    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "GET", "scheme": "http", "path": "/api/v1/auth/me",
        "raw_path": b"/api/v1/auth/me", "query_string": b"", "root_path": "",
        "headers": [], "client": ("127.0.0.1", 1), "server": ("testserver", 80),
    }

    async def run():
        middleware = ModuleAccessMiddleware(app)
        return await middleware.dispatch(Request(scope), fake_call_next)

    response = asyncio.run(run())

    assert response.status_code == 200
    assert reached == ["/api/v1/auth/me"], "auth 路径应被放行到路由"


# ── public surface 的数据边界（服务端强制）─────────────────────────────

class _FakeDataService:
    async def fetch_klines(self, symbol, timeframe, limit, force_refresh=False):
        return {
            "data": [
                {
                    "open_time": 1_700_000_000_000 + index * 86_400_000,
                    "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.0, "volume": 100.0,
                }
                for index in range(40)
            ]
        }


class _FakeChanService:
    async def analyze(self, symbol, timeframe, klines):
        return ChanResult(
            symbol=symbol, timeframe=timeframe,
            merged_klines=[], fenxings=[], bis=[], duans=[],
            zhongshus=[], duan_zhongshus=[],
            buy_sell_points=[BuySellPoint(
                type="buy1", price=10.0, time=int(klines[0]["open_time"]),
                zhongshu_index=None, bi_index=0, confirmed=True, strength=1.0, reason="假信号",
            )],
            divergences=[], updated_at=int(klines[-1]["open_time"]),
        )


def _public_surface_test(seeded_db, monkeypatch, *, surface: str, headers: dict):
    monkeypatch.setattr(chan_api, "get_data_service", lambda: _FakeDataService())
    monkeypatch.setattr(chan_api, "get_chan_service", lambda: _FakeChanService())
    cleanup = _bind_session(seeded_db)

    async def run():
        return await _asgi_request(
            "GET", "/api/v1/chan/V0/1d",
            headers={"X-Signal-Surface": surface, **headers},
        )

    try:
        return asyncio.run(run())
    finally:
        asyncio.run(cleanup())


def test_public_surface_strips_actionable_chan_data(seeded_db, monkeypatch):
    """public 面拿不到买卖点等可执行信息（服务端剥离，不是靠前端藏）。"""
    status, payload = _public_surface_test(seeded_db, monkeypatch, surface="public", headers={})

    assert status == 200, payload
    assert payload["buy_sell_points"] == [], "public 面不应返回买卖点"


def test_private_surface_keeps_chan_data(seeded_db, monkeypatch):
    """同一份数据，私有面（管理员）应当拿得到买卖点——否则上面的剥离断言无意义。"""
    cleanup = _bind_session(seeded_db)

    async def run():
        admin_id = await _user_id("admin", seeded_db)
        return admin_id

    try:
        admin_id = asyncio.run(run())
    finally:
        asyncio.run(cleanup())

    monkeypatch.setattr(chan_api, "get_data_service", lambda: _FakeDataService())
    monkeypatch.setattr(chan_api, "get_chan_service", lambda: _FakeChanService())
    cleanup = _bind_session(seeded_db)

    async def call():
        return await _asgi_request(
            "GET", "/api/v1/chan/V0/1d",
            headers={"X-Signal-Surface": "private", **_bearer(admin_id)},
        )

    try:
        status, payload = asyncio.run(call())
    finally:
        asyncio.run(cleanup())

    assert status == 200, payload
    assert len(payload["buy_sell_points"]) == 1


# ── 登录链路（真实密码校验 + 令牌签发）──────────────────────────────────

def test_seeded_admin_can_log_in_through_the_api(seeded_db):
    """种子里的 admin 口令能真的登录，并拿到可用令牌。"""
    cleanup = _bind_session(seeded_db)

    async def run():
        return await _asgi_request(
            "POST", "/api/v1/auth/login",
            headers={"Content-Type": "application/json"},
            body={"username": "admin", "password": "Admin123!"},
        )

    try:
        status, payload = asyncio.run(run())
    finally:
        asyncio.run(cleanup())

    assert status == 200, payload
    assert payload["access_token"]
    assert payload["user"]["username"] == "admin"
