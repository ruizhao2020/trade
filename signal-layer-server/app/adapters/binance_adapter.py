"""
============================================================================
MySQL A-stock 数据适配器
============================================================================

## 功能
从 MySQL 数据库读取 A 股 K 线数据。
数据库表命名规则: {code}_{market}_{timeframe}  如 000610_sz_日线
"""

from __future__ import annotations
import asyncio
import logging
from typing import Awaitable, Callable
from app.adapters.base import DataAdapter
from app.market_data.mysql_store import (
    MYSQL_CONFIG,
    TIMEFRAME_MINUTES as TF_MINUTES,
    TIMEFRAME_SUFFIX as TF_MAP,
)

logger = logging.getLogger(__name__)

_conn = None

def _get_conn():
    global _conn
    try:
        if _conn and _conn.open:
            _conn.ping(reconnect=True)
            return _conn
    except Exception:
        _conn = None
    import pymysql
    _conn = pymysql.connect(**MYSQL_CONFIG)
    return _conn

def _query_kline(symbol: str, timeframe: str, limit: int = 500) -> list[dict]:
    """同步查询 MySQL（被 asyncio.to_thread 包装）。每次创建新连接避免并发冲突"""
    tf_suffix = TF_MAP.get(timeframe)
    if not tf_suffix:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    tbl = f"{symbol}_{tf_suffix}"
    import pymysql
    conn = pymysql.connect(**MYSQL_CONFIG)
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT date_time_int, open, close, high, low, volume "
            f"FROM `{tbl}` ORDER BY date_time_int DESC LIMIT {limit}"
        )
        rows = cur.fetchall()
        rows = list(reversed(rows))
        return [
            {
                'open_time': int(r[0]) * 1000,
                'open': float(r[1]), 'close': float(r[2]),
                'high': float(r[3]), 'low': float(r[4]),
                'volume': float(r[5]) * 100,
                'is_closed': True,
            }
            for r in rows
        ]
    finally:
        conn.close()


class BinanceAdapter(DataAdapter):
    """MySQL A-stock 数据适配器（保留 BinanceAdapter 类名以兼容现有代码）"""

    @property
    def name(self) -> str:
        return "mysql"

    async def fetch_klines(
        self, symbol: str, timeframe: str,
        start_time: int | None = None, end_time: int | None = None, limit: int = 500,
    ) -> list[dict]:
        logger.info(f"fetch_klines symbol={symbol} tf={timeframe} limit={limit}")
        # 在 thread pool 中运行同步 MySQL 查询
        return await asyncio.to_thread(_query_kline, symbol, timeframe, limit)

    async def subscribe_klines(
        self, symbol: str, timeframe: str, callback: Callable[[dict], Awaitable[None]],
    ) -> Callable[[], Awaitable[None]]:
        # A 股不支持实时推送，返回空取消函数
        async def _noop(): pass
        return _noop

    def supported_timeframes(self) -> list[str]:
        return list(TF_MAP.keys())

    def timeframe_to_exchange(self, timeframe: str) -> str:
        return TF_MAP.get(timeframe, timeframe)
