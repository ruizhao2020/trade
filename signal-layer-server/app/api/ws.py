import json
import asyncio
import time
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.api.deps import get_data_service

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


manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
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
