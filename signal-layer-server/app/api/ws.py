from __future__ import annotations

import json
import asyncio
import time
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from app.api.deps import get_data_service
from app.db import get_session
from app.models.auth import User
from app.services.auth_service import decode_access_token, permission_codes, status_rejection_message

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self._connections: dict[str, WebSocket] = {}
        self._subscriptions: dict[str, set[str]] = {}
        self._channel_subscribers: dict[str, set[str]] = {}
        self._counter = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"ws_{self._counter}"

    async def connect(self, ws: WebSocket) -> str:
        await ws.accept()
        client_id = self._next_id()
        self._connections[client_id] = ws
        self._subscriptions[client_id] = set()
        logger.info(f"WebSocket connected: {client_id} (total: {len(self._connections)})")
        return client_id

    def subscribe(self, client_id: str, channel: str, key: str):
        if client_id not in self._subscriptions:
            logger.warning(f"Subscribe from unknown client: {client_id}")
            return
        chan_key = f"{channel}:{key}"
        self._subscriptions[client_id].add(chan_key)
        if chan_key not in self._channel_subscribers:
            self._channel_subscribers[chan_key] = set()
        self._channel_subscribers[chan_key].add(client_id)
        logger.info(f"WebSocket {client_id} subscribed to {chan_key}")

    def unsubscribe(self, client_id: str, channel: str, key: str):
        chan_key = f"{channel}:{key}"
        if client_id in self._subscriptions:
            self._subscriptions[client_id].discard(chan_key)
        if chan_key in self._channel_subscribers:
            self._channel_subscribers[chan_key].discard(client_id)

    async def broadcast(self, channel: str, key: str, message: dict):
        chan_key = f"{channel}:{key}"
        subs = self._channel_subscribers.get(chan_key, set())
        dead: list[str] = []
        for cid in subs:
            ws = self._connections.get(cid)
            if ws is None:
                dead.append(cid)
                continue
            try:
                await ws.send_json(message)
            except Exception:
                logger.debug(f"Broadcast to {cid} failed, removing")
                dead.append(cid)
        for cid in dead:
            await self.disconnect(cid)
        if subs:
            logger.debug(f"Broadcast {chan_key} to {len(subs)} subscribers")

    async def broadcast_all(self, channel: str, message: dict):
        for cid, subs in self._subscriptions.items():
            for s in subs:
                if s.startswith(channel):
                    ws = self._connections.get(cid)
                    if ws:
                        try:
                            await ws.send_json(message)
                        except Exception:
                            pass

    async def mock_kline_stream(self, symbol: str, timeframe: str):
        ds = get_data_service()
        logger.info(f"Starting mock kline stream for {symbol} {timeframe}")
        while True:
            klines = await ds.fetch_klines(symbol, timeframe, limit=1)
            if klines["data"]:
                k = klines["data"][-1]
                await self.broadcast("kline", f"{symbol}:{timeframe}", {
                    "type": "kline_update",
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "kline": k,
                })
            await asyncio.sleep(5)

    async def disconnect(self, client_id: str):
        if client_id in self._subscriptions:
            for chan_key in self._subscriptions[client_id]:
                if chan_key in self._channel_subscribers:
                    self._channel_subscribers[chan_key].discard(client_id)
            del self._subscriptions[client_id]
        self._connections.pop(client_id, None)
        logger.info(f"WebSocket disconnected: {client_id} (remaining: {len(self._connections)})")


# 订阅频道 -> 所需权限。
#
# 必须在此登记：模块准入中间件是 BaseHTTPMiddleware，而它对非 http scope
# （也就是 WebSocket）直接放行，所以 ws 的授权只能在路由这一层做。
# 这里做成"查表 + 未登记即拒绝"，让"新增频道忘了加权限检查"在结构上不可能发生。
CHANNEL_PERMISSIONS: dict[str, str] = {
    "kline": "market.read",
    "signal": "strategy.evaluate",
}


def authorize_channel(channel: str, permissions: set[str]) -> str | None:
    """返回 None 表示放行，否则返回拒绝原因。未知频道一律拒绝（fail-closed）。"""
    required = CHANNEL_PERMISSIONS.get(channel)
    if required is None:
        return f"未知订阅频道：{channel}"
    if required not in permissions:
        return f"缺少权限：{required}"
    return None


manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    token = ws.query_params.get("token", "")
    try:
        user_id = decode_access_token(token)
        user = None
        # 显式 aclose()：`async for ... break` 不会关闭生成器，只能等 GC，
        # 会导致连接未归还连接池（每个 ws 连接漏一个）。
        sessions = get_session()
        try:
            async for session in sessions:
                user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
                break
        finally:
            await sessions.aclose()
        if not user or not user.enabled:
            raise ValueError("用户不可用")
        if status_rejection_message(user.status):
            raise ValueError("账号未通过审核")
        permissions = permission_codes(user)
    except ValueError:
        await ws.close(code=4401, reason="请先登录")
        return
    except Exception:
        # 鉴权阶段的服务端异常也必须关闭连接（fail-closed），不能放行
        logger.exception("WebSocket 鉴权阶段失败")
        await ws.close(code=1011, reason="服务暂时不可用")
        return

    client_id = await manager.connect(ws)
    logger.info(f"WebSocket connection established: {client_id}")

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning(f"WebSocket {client_id} sent invalid JSON")
                await ws.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = msg.get("type")
            logger.debug(f"WebSocket {client_id} msg: {msg_type}")

            if msg_type == "subscribe":
                channel = msg.get("channel", "")
                # 统一的授权入口：未登记的频道直接拒绝，不再逐个频道手写权限判断
                denied = authorize_channel(channel, permissions)
                if denied:
                    logger.warning(f"WebSocket {client_id} subscribe 被拒: {denied}")
                    await ws.send_json({"type": "error", "message": denied})
                    continue
                if channel == "kline":
                    symbol = msg.get("symbol", "")
                    timeframe = msg.get("timeframe", "")
                    channel_key = f"{symbol}:{timeframe}"
                    manager.subscribe(client_id, "kline", channel_key)
                    await ws.send_json({
                        "type": "subscribed",
                        "channel": "kline",
                        "key": channel_key,
                    })
                elif channel == "signal":
                    template_id = msg.get("template_id", "")
                    manager.subscribe(client_id, "signal", template_id)
                    await ws.send_json({
                        "type": "subscribed",
                        "channel": "signal",
                        "key": template_id,
                    })

            elif msg_type == "unsubscribe":
                channel = msg.get("channel", "")
                if channel == "kline":
                    symbol = msg.get("symbol", "")
                    timeframe = msg.get("timeframe", "")
                    manager.unsubscribe(client_id, "kline", f"{symbol}:{timeframe}")
                    logger.info(f"WebSocket {client_id} unsubscribed from kline:{symbol}:{timeframe}")
                elif channel == "signal":
                    template_id = msg.get("template_id", "")
                    manager.unsubscribe(client_id, "signal", template_id)
                    logger.info(f"WebSocket {client_id} unsubscribed from signal:{template_id}")

            elif msg_type == "ping":
                await ws.send_json({"type": "pong", "timestamp": int(time.time() * 1000)})
                logger.debug(f"WebSocket {client_id} pong sent")

            else:
                logger.warning(f"WebSocket {client_id} unknown msg type: {msg_type}")
                await ws.send_json({"type": "error", "message": f"Unknown type: {msg_type}"})

    except WebSocketDisconnect:
        logger.info(f"WebSocket {client_id} disconnected")
        await manager.disconnect(client_id)
