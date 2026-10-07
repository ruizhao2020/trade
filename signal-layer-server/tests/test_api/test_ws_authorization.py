"""WebSocket 订阅频道的授权与连接路径。

背景：模块准入中间件是 `BaseHTTPMiddleware`，它对非 http scope（即 WebSocket）
直接转发、不做任何检查，所以 ws 的授权只能在路由这一层保证。因此这里刻意做成
"查表 + 未登记即拒绝"，测试要覆盖 fail-closed 行为。

连接路径用伪造 WebSocket + monkeypatch 驱动（与 tests/test_api 里其它用例一致），
不引入 websocket 客户端依赖。
"""

from __future__ import annotations

import asyncio
import json

import pytest

from app.api import ws as ws_module
from app.api.ws import CHANNEL_PERMISSIONS, authorize_channel
from app.models.auth import Module, Permission, Role, User
from app.services.auth_service import create_access_token


# ── 频道授权规则 ────────────────────────────────────────────────────────

def test_known_channels_are_gated_by_their_permission():
    assert authorize_channel("kline", {"market.read"}) is None
    assert authorize_channel("signal", {"strategy.evaluate"}) is None

    assert "market.read" in (authorize_channel("kline", {"strategy.evaluate"}) or "")
    assert "strategy.evaluate" in (authorize_channel("signal", {"market.read"}) or "")
    assert authorize_channel("kline", set()) is not None


def test_unknown_channel_is_rejected():
    """未登记的频道一律拒绝——这是"新增频道不会漏掉权限检查"的保证。"""
    reason = authorize_channel("something_new", {"market.read", "strategy.evaluate"})

    assert reason is not None
    assert "未知订阅频道" in reason


def test_every_registered_channel_declares_a_permission():
    for channel, permission in CHANNEL_PERMISSIONS.items():
        assert channel and permission, f"频道 {channel} 的权限声明不完整"


def test_channel_names_are_case_sensitive():
    """大小写不同即视为未登记，避免用 `KLINE` 之类变体绕过权限映射。"""
    assert authorize_channel("KLINE", {"market.read"}) is not None
    assert authorize_channel("", {"market.read"}) is not None


# ── 连接路径（伪造 WebSocket）────────────────────────────────────────────

def make_user(*permission_codes: str, enabled: bool = True) -> User:
    role = Role(id=1, code="reader", name="只读用户", enabled=True)
    role.permissions = [
        Permission(id=index + 1, code=code, name=code)
        for index, code in enumerate(permission_codes)
    ]
    user = User(id=1, username="reader", display_name="只读用户", password_hash="x", enabled=enabled)
    user.roles = [role]
    return user


class FakeWebSocket:
    """只实现 handler 用到的接口。"""

    def __init__(self, token: str = "", incoming: list[str] | None = None):
        self.query_params = {"token": token}
        self._incoming = list(incoming or [])
        self.closed: tuple[int, str] | None = None
        self.accepted = False
        self.sent: list[dict] = []

    async def close(self, code: int = 1000, reason: str = ""):
        self.closed = (code, reason)

    async def accept(self):
        self.accepted = True

    async def send_json(self, data: dict):
        self.sent.append(data)

    async def receive_text(self) -> str:
        if self._incoming:
            return self._incoming.pop(0)
        raise ws_module.WebSocketDisconnect()


def bind_session(monkeypatch, user: User | None):
    """把 handler 里的 get_session 换成返回指定用户的假会话。"""

    class FakeResult:
        def scalar_one_or_none(self):
            return user

    class FakeSession:
        async def execute(self, *_args, **_kwargs):
            return FakeResult()

    async def fake_get_session():
        yield FakeSession()

    monkeypatch.setattr(ws_module, "get_session", fake_get_session)


def test_connection_without_token_is_rejected(monkeypatch):
    ws = FakeWebSocket(token="")
    asyncio.run(ws_module.websocket_endpoint(ws))

    assert ws.closed is not None
    assert ws.closed[0] == 4401
    assert ws.accepted is False, "未通过鉴权不应 accept"


def test_connection_with_bogus_token_is_rejected(monkeypatch):
    bind_session(monkeypatch, None)
    ws = FakeWebSocket(token="not-a-real-token")
    asyncio.run(ws_module.websocket_endpoint(ws))

    assert ws.closed is not None and ws.closed[0] == 4401
    assert ws.accepted is False


def test_connection_with_unknown_user_is_rejected(monkeypatch):
    token, _ = create_access_token(999)  # 令牌有效，但库里没有这个用户
    bind_session(monkeypatch, None)
    ws = FakeWebSocket(token=token)
    asyncio.run(ws_module.websocket_endpoint(ws))

    assert ws.closed is not None and ws.closed[0] == 4401
    assert ws.accepted is False


def test_disabled_user_is_rejected(monkeypatch):
    token, _ = create_access_token(1)
    bind_session(monkeypatch, make_user("market.read", enabled=False))
    ws = FakeWebSocket(token=token)
    asyncio.run(ws_module.websocket_endpoint(ws))

    assert ws.closed is not None and ws.closed[0] == 4401


def test_unapproved_user_is_rejected(monkeypatch):
    """待审核账号即便持有合法令牌也不能连 ws（与 http 侧的审核门一致）。"""
    for status in ("pending", "rejected"):
        token, _ = create_access_token(1)
        user = make_user("market.read", "strategy.evaluate")
        user.status = status
        bind_session(monkeypatch, user)
        ws = FakeWebSocket(token=token, incoming=[json.dumps({"type": "subscribe", "channel": "kline"})])

        asyncio.run(ws_module.websocket_endpoint(ws))

        assert ws.closed is not None and ws.closed[0] == 4401, f"{status} 账号不应连上 ws"
        assert ws.accepted is False
        assert ws.sent == []


def test_authorized_connection_accepts_and_survives_disconnect(monkeypatch):
    """鉴权通过后应 accept；客户端断开时干净退出（不抛异常）。"""
    token, _ = create_access_token(1)
    bind_session(monkeypatch, make_user("market.read"))
    ws = FakeWebSocket(token=token)

    asyncio.run(ws_module.websocket_endpoint(ws))

    assert ws.accepted is True
    assert ws.closed is None, "正常断开不应再走 close 分支"


def test_unknown_subscribe_channel_is_refused_over_the_wire(monkeypatch):
    """处理函数必须真的查注册表：未知频道返回错误帧而不是订阅成功。"""
    token, _ = create_access_token(1)
    bind_session(monkeypatch, make_user("market.read", "strategy.evaluate"))
    ws = FakeWebSocket(token=token, incoming=[json.dumps({"type": "subscribe", "channel": "backdoor"})])

    asyncio.run(ws_module.websocket_endpoint(ws))

    assert ws.accepted is True
    assert ws.sent, "应当回一个错误帧"
    assert "未知订阅频道" in ws.sent[0]["message"]
    assert not any(item.get("type") == "subscribed" for item in ws.sent)


def test_subscribe_without_permission_is_refused(monkeypatch):
    token, _ = create_access_token(1)
    bind_session(monkeypatch, make_user("market.read"))  # 有行情权限，无策略评估权限
    ws = FakeWebSocket(token=token, incoming=[json.dumps({"type": "subscribe", "channel": "signal"})])

    asyncio.run(ws_module.websocket_endpoint(ws))

    assert ws.sent and "strategy.evaluate" in ws.sent[0]["message"]
    assert not any(item.get("type") == "subscribed" for item in ws.sent)


def test_subscribe_with_permission_succeeds(monkeypatch):
    token, _ = create_access_token(1)
    bind_session(monkeypatch, make_user("market.read"))
    ws = FakeWebSocket(token=token, incoming=[
        json.dumps({"type": "subscribe", "channel": "kline", "symbol": "V0", "timeframe": "1d"}),
    ])

    asyncio.run(ws_module.websocket_endpoint(ws))

    assert any(item.get("type") == "subscribed" for item in ws.sent), ws.sent
