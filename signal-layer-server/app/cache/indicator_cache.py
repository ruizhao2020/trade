from __future__ import annotations
import json
import logging
from typing import Any
from redis.asyncio import Redis
from app.config import settings

logger = logging.getLogger(__name__)


class IndicatorCache:
    def __init__(self, redis: Redis | None):
        self._redis = redis
        self._ttl = settings.cache_ttl
        self._mem: dict[str, dict] = {}

    async def get(self, key: str) -> dict | None:
        if key in self._mem:
            logger.debug(f"Cache GET {key} -> HIT (memory)")
            return self._mem[key]
        if self._redis is None:
            return None
        try:
            val = await self._redis.get(key)
            if val is None:
                return None
            data = json.loads(val)
            self._mem[key] = data
            return data
        except Exception:
            return None

    async def set(self, key: str, value: dict, ttl: int | None = None) -> None:
        self._mem[key] = value
        if self._redis is None:
            return
        effective_ttl = ttl or self._ttl
        try:
            data = json.dumps(value, default=str)
            await self._redis.setex(key, effective_ttl, data)
        except Exception:
            pass


def key_chan(symbol: str, timeframe: str) -> str:
    # v2: 线段边界连续性修正 + 背驰详情原因，避免读取旧算法缓存。
    return f"chan:v2:{symbol}:{timeframe}"


def key_indicator(symbol: str, timeframe: str, indicator_type: str, params: dict[str, Any]) -> str:
    params_str = "_".join(f"{k}={v}" for k, v in sorted(params.items()))
    # v3: 筹码分布补充逐 K 线快照，隔离旧结构缓存。
    return f"indicator:v3:{symbol}:{timeframe}:{indicator_type}:{params_str}"
