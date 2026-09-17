from __future__ import annotations

import logging

from app.adapters.akshare_adapter import AkShareAdapter
from app.adapters.base import DataAdapter
from app.adapters.futures_adapter import FuturesAdapter
from app.market_data.manager import MarketDataManager
from app.market_data.mysql_store import MySQLMarketDataStore

logger = logging.getLogger(__name__)


class DataService:
    """行情服务门面；查库、缺口计算、API 补齐统一交给 MarketDataManager。"""

    def __init__(
        self,
        adapter: DataAdapter | None = None,
        *,
        store=None,
        futures_adapter: DataAdapter | None = None,
    ):
        self._stock_source = adapter or AkShareAdapter()
        self._futures_source = futures_adapter or FuturesAdapter(allow_mock=False)
        self._manager = MarketDataManager(
            store or MySQLMarketDataStore(),
            self._stock_source,
            self._futures_source,
        )
        logger.info(
            "DataService initialized: store=mysql-per-symbol-table stock_api=%s futures_api=%s",
            self._stock_source.name,
            self._futures_source.name,
        )

    async def fetch_klines(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 200,
        force_refresh: bool = False,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> dict:
        bars, from_database = await self._manager.fetch(
            symbol,
            timeframe,
            limit=limit,
            start_time=start_time,
            end_time=end_time,
            force_refresh=force_refresh,
        )
        status = self._manager.latest_status(symbol, timeframe) if start_time is None else {}
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "data": bars,
            "from_time": bars[0]["open_time"] if bars else None,
            "to_time": bars[-1]["open_time"] if bars else None,
            "count": len(bars),
            "cached": from_database,
            "stale": bool(status.get("stale", False)),
            "refresh_failed": bool(status.get("refresh_failed", False)),
            "expected_time": status.get("expected_time"),
            "status_message": status.get("message"),
        }

    async def subscribe(self, symbol: str, timeframe: str, on_kline):
        source = self._futures_source if symbol and symbol[0].isalpha() else self._stock_source
        return await source.subscribe_klines(symbol, timeframe, on_kline)

    @property
    def adapter(self):
        """兼容旧调用方；返回股票外部行情源。"""
        return self._stock_source
