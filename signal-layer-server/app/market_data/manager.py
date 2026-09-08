from __future__ import annotations

import asyncio
import logging
import math
from typing import Protocol

from app.adapters.base import DataAdapter
from app.market_data.ranges import TimeRange, infer_coverage, missing_ranges
from app.market_data.mysql_store import TIMEFRAME_MINUTES

logger = logging.getLogger(__name__)


class MarketDataStore(Protocol):
    def fetch_latest(self, symbol: str, timeframe: str, limit: int) -> list[dict]: ...
    def fetch_range(self, symbol: str, timeframe: str, start_time: int, end_time: int) -> list[dict]: ...
    def upsert(self, symbol: str, timeframe: str, bars: list[dict]): ...
    def coverage(self, symbol: str, timeframe: str) -> list[tuple[int, int]]: ...
    def add_coverage(self, symbol: str, timeframe: str, start_time: int, end_time: int): ...


class MarketDataManager:
    """统一管理行情读取：始终先查 DB，只向外部 API 请求缺失部分并回写 DB。"""

    def __init__(
        self,
        store: MarketDataStore,
        stock_source: DataAdapter,
        futures_source: DataAdapter,
    ):
        self._store = store
        self._stock_source = stock_source
        self._futures_source = futures_source
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}

    def _source(self, symbol: str) -> DataAdapter:
        return self._futures_source if symbol and symbol[0].isalpha() else self._stock_source

    @staticmethod
    def _range_limit(timeframe: str, requested: TimeRange) -> int:
        interval_ms = TIMEFRAME_MINUTES[timeframe] * 60 * 1000
        return min(max(math.ceil((requested.end - requested.start) / interval_ms) + 1, 1), 100_000)

    async def _store_call(self, method: str, *args):
        try:
            return await asyncio.to_thread(getattr(self._store, method), *args)
        except Exception:
            if not getattr(self._store, "retry_transient", False):
                raise
            logger.warning("market DB operation %s failed; retrying once", method, exc_info=True)
            await asyncio.sleep(0.15)
            return await asyncio.to_thread(getattr(self._store, method), *args)

    async def fetch(
        self,
        symbol: str,
        timeframe: str,
        *,
        limit: int = 200,
        start_time: int | None = None,
        end_time: int | None = None,
        force_refresh: bool = False,
    ) -> tuple[list[dict], bool]:
        if timeframe not in TIMEFRAME_MINUTES:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        if (start_time is None) != (end_time is None):
            raise ValueError("start_time and end_time must be provided together")
        lock = self._locks.setdefault((symbol, timeframe), asyncio.Lock())
        async with lock:
            if start_time is not None and end_time is not None:
                return await self._fetch_range(
                    symbol, timeframe, TimeRange(start_time, end_time), force_refresh=force_refresh,
                )
            return await self._fetch_latest(symbol, timeframe, limit, force_refresh=force_refresh)

    async def _fetch_latest(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
        *,
        force_refresh: bool,
    ) -> tuple[list[dict], bool]:
        stored = await self._store_call("fetch_latest", symbol, timeframe, limit)
        if len(stored) >= limit and not force_refresh:
            return stored[-limit:], True

        source = self._source(symbol)
        fetched = await source.fetch_klines(symbol, timeframe, limit=limit)
        await self._store_call("upsert", symbol, timeframe, fetched)
        if fetched:
            await self._store_call(
                "add_coverage", symbol, timeframe,
                min(int(bar["open_time"]) for bar in fetched),
                max(int(bar["open_time"]) for bar in fetched),
            )
        complete = await self._store_call("fetch_latest", symbol, timeframe, limit)
        return complete[-limit:], False

    async def _fetch_range(
        self,
        symbol: str,
        timeframe: str,
        requested: TimeRange,
        *,
        force_refresh: bool,
    ) -> tuple[list[dict], bool]:
        stored = await self._store_call("fetch_range", symbol, timeframe, requested.start, requested.end)
        coverage_rows = await self._store_call("coverage", symbol, timeframe)
        covered = [TimeRange(start, end) for start, end in coverage_rows]

        if not covered and stored:
            inferred = infer_coverage([int(bar["open_time"]) for bar in stored], timeframe)
            for item in inferred:
                await self._store_call("add_coverage", symbol, timeframe, item.start, item.end)
            covered = inferred

        gaps = [requested] if force_refresh else missing_ranges(requested, covered)
        if not gaps:
            return stored, True

        source = self._source(symbol)
        for gap in gaps:
            logger.info(
                "market data gap %s %s [%s, %s], fetching from %s",
                symbol, timeframe, gap.start, gap.end, source.name,
            )
            fetched = await source.fetch_klines(
                symbol,
                timeframe,
                start_time=gap.start,
                end_time=gap.end,
                limit=self._range_limit(timeframe, gap),
            )
            await self._store_call("upsert", symbol, timeframe, fetched)
            if source.range_authoritative:
                await self._store_call("add_coverage", symbol, timeframe, gap.start, gap.end)
            elif fetched:
                fetched_start = max(gap.start, min(int(bar["open_time"]) for bar in fetched))
                fetched_end = min(gap.end, max(int(bar["open_time"]) for bar in fetched))
                await self._store_call("add_coverage", symbol, timeframe, fetched_start, fetched_end)

        complete = await self._store_call("fetch_range", symbol, timeframe, requested.start, requested.end)
        return complete, False
