"""
============================================================================
标的列表接口
============================================================================

## 功能
提供品种列表查询，供前端品种搜索/下拉框使用。

## 市场路由
- market=stock   → 从 MySQL stock_info 表读取 A 股列表（含行业分类）
- market=futures → 用 AKShare futures_display_main_sina() 拉主力合约列表
"""

from __future__ import annotations
import logging
import asyncio
import time
from typing import Optional
from fastapi import APIRouter, Query, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/symbols", tags=["symbols"])


# ---- 期货列表缓存 ------------------------------------------------------------
# 期货主力合约列表变化极不频繁（主力连续代码 RB0/V0 基本固定），
# 缓存 24 小时，避免每次请求都实时调新浪接口（约 15 秒延迟）。

_futures_cache: dict = {"data": None, "ts": 0.0}
_FUTURES_CACHE_TTL = 24 * 3600  # 24 小时


# ---- MySQL A 股列表 ---------------------------------------------------------

_MYSQL_CONFIG = {
    "host": "gz-cdb-qp23sl8p.sql.tencentcdb.com",
    "port": 23784,
    "user": "root",
    "password": "stock2026",
    "database": "stock",
    "connect_timeout": 15,
    "read_timeout": 20,
}


def _fetch_stock_symbols(keyword: Optional[str], limit: int) -> tuple[list[dict], int]:
    """从 MySQL stock_info 表读取股票列表，支持关键字搜索。

    返回 (符号列表, 符合条件的总数)。
    """
    import pymysql

    conn = pymysql.connect(**_MYSQL_CONFIG)
    try:
        cur = conn.cursor()

        # 构建 WHERE 条件
        if keyword:
            where = "WHERE code LIKE %s OR name LIKE %s"
            params: tuple = (f"%{keyword}%", f"%{keyword}%")
        else:
            where = ""
            params = ()

        # 1. 查总数
        cur.execute(f"SELECT COUNT(*) FROM stock_info {where}", params)
        total = cur.fetchone()[0]

        # 2. 查当前页数据
        cur.execute(
            f"SELECT code, name, industry FROM stock_info {where} ORDER BY code LIMIT %s",
            (*params, limit),
        )
        rows = cur.fetchall()
        symbols = [
            {
                "symbol": r[0].replace(".", "_").lower(),  # 000001.SZ → 000001_sz
                "code": r[0],
                "name": r[1],
                "industry": r[2],
                "market": "stock",
            }
            for r in rows
        ]
        return symbols, total
    finally:
        conn.close()


# ---- AKShare 期货主力合约列表 -------------------------------------------------

def _fetch_futures_symbols() -> list[dict]:
    """用 AKShare 拉取国内期货主力连续合约列表。"""
    import akshare as ak

    df = ak.futures_display_main_sina()
    if df is None or df.empty:
        return []

    return [
        {
            "symbol": row.get("symbol", ""),  # 如 RB0（主力连续）
            "name": row.get("name", ""),
            "exchange": row.get("exchange", ""),
            "market": "futures",
        }
        for _, row in df.iterrows()
    ]


def _fetch_futures_symbols_cached() -> list[dict]:
    """带缓存的期货列表获取。TTL 内直接返回缓存，避免每次实时调新浪接口。"""
    global _futures_cache
    now = time.time()
    if _futures_cache["data"] is not None and (now - _futures_cache["ts"]) < _FUTURES_CACHE_TTL:
        return _futures_cache["data"]

    data = _fetch_futures_symbols()
    _futures_cache = {"data": data, "ts": now}
    logger.info(f"futures symbols cached: {len(data)} items")
    return data


def _warmup_futures_symbols():
    """后端启动时后台预热期货列表缓存，避免用户首次请求等待 15 秒。"""
    import threading

    def _run():
        try:
            _fetch_futures_symbols_cached()
            logger.info("futures symbols warmed up")
        except Exception as e:
            logger.warning(f"futures symbols warmup failed: {e}")

    t = threading.Thread(target=_run, daemon=True)
    t.start()


# 模块加载时（后端启动）自动后台预热
_warmup_futures_symbols()


# ---- 路由 -------------------------------------------------------------------

async def get_symbol_items(
    market: str,
    keyword: Optional[str],
    limit: int,
) -> tuple[list[dict], int]:
    """返回标的列表和匹配总数，供 HTTP 路由及选股服务复用。"""
    if market == "futures":
        all_symbols = await asyncio.to_thread(_fetch_futures_symbols_cached)
        if keyword:
            normalized = keyword.strip().lower()
            filtered = [
                item for item in all_symbols
                if normalized in item["name"].lower() or normalized in item["symbol"].lower()
            ]
        else:
            filtered = all_symbols
        return filtered[:limit], len(filtered)
    if market == "stock":
        return await asyncio.to_thread(_fetch_stock_symbols, keyword, limit)
    raise ValueError(f"不支持的市场类型: {market}，可选 stock / futures")


@router.get("")
async def list_symbols(
    market: str = Query(default="stock", description="市场类型：stock=股票, futures=期货"),
    keyword: Optional[str] = Query(default=None, description="搜索关键字（股票代码或名称）"),
    limit: int = Query(default=200, ge=1, le=2000),
):
    """查询品种列表。"""
    try:
        symbols, total = await get_symbol_items(market, keyword, limit)
        return {"market": market, "total": total, "count": len(symbols), "symbols": symbols}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        logger.error(f"{market} symbols fetch failed: {error}")
        raise HTTPException(status_code=500, detail=f"标的列表获取失败: {error}") from error
