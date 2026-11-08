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


def key_chan(symbol: str, timeframe: str, divergence_power_ratio: float = 0.7, window: int | None = None) -> str:
    # v3: 缓存包含背驰力度阈值，配置修改后不会复用旧结果。
    # v4: 缓存值新增 data_start_time/data_count，命中时要求覆盖请求区间；
    #     旧版本只记录终点，会把 200 根的缠论结果复用给 500 根的请求。
    # v5: 窗口长度并入 key。缠论结构随窗口变化（笔/中枢数量不同），
    #     选股用 200 根、图表用 500 根，若共用一个 key，结果会取决于谁先写入。
    # v6: 新增 overlaps（K 线重叠级别），旧缓存没有这个字段。
    # v7: 新增 classification（走势完全分类），旧缓存没有这个字段。
    # v8: classification 增加 children（二级分类），旧缓存没有这个字段。
    # v9: 段改为"特征序列基础线段 + 走势回抽合并"，段划分与旧版本不同。
    # v10: 首笔单独成段时跳过，段从趋势起点开始（不再把后段拉回首笔起点）。
    window_part = f":window={window}" if window is not None else ""
    return f"chan:v10:{symbol}:{timeframe}{window_part}:divergence={divergence_power_ratio:.6f}"


def key_indicator(symbol: str, timeframe: str, indicator_type: str, params: dict[str, Any]) -> str:
    params_str = "_".join(f"{k}={v}" for k, v in sorted(params.items()))
    # v7: MA 增加支撑/压制序列，避免复用缺少新字段的旧缓存。
    # v8: MACD 增加顶/底背驰事件与箭头，旧缓存没有这两个字段、也没有 arrows。
    return f"indicator:v8:{symbol}:{timeframe}:{indicator_type}:{params_str}"
