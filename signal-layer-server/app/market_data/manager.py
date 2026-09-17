from __future__ import annotations

import asyncio
import logging
import math
import time
from collections import OrderedDict
from datetime import datetime, time as datetime_time, timedelta, timezone
from typing import Callable, Protocol

from app.adapters.base import DataAdapter
from app.market_data.ranges import TimeRange, infer_coverage, missing_ranges
from app.market_data.mysql_store import TIMEFRAME_MINUTES

logger = logging.getLogger(__name__)

_LATEST_CACHE_TTL = {"5m": 15.0, "15m": 30.0, "30m": 60.0, "60m": 90.0, "1d": 300.0}
_LATEST_CACHE_MAX_ENTRIES = 128
_CN_TZ = timezone(timedelta(hours=8))


def expected_latest_daily_open_time(now_ms: int | None = None) -> int:
    """最近应当已经完成的交易日（日线按前一工作日保守判断）。"""
    now = datetime.fromtimestamp((now_ms or int(time.time() * 1000)) / 1000, tz=_CN_TZ)
    candidate = now.date() - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return int(datetime.combine(candidate, datetime_time.min, tzinfo=_CN_TZ).timestamp() * 1000)


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
        now_ms: Callable[[], int] | None = None,
    ):
        self._store = store
        self._stock_source = stock_source
        self._futures_source = futures_source
        self._now_ms = now_ms or (lambda: int(time.time() * 1000))
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}
        self._enrichment_tasks: dict[tuple[str, str], asyncio.Task] = {}
        self._latest_cache: OrderedDict[
            tuple[str, str], tuple[float, int, list[dict]]
        ] = OrderedDict()
        self._latest_status: dict[tuple[str, str], dict] = {}

    def _is_latest_fresh(self, timeframe: str, bars: list[dict]) -> bool:
        if not bars:
            return False
        if timeframe != "1d":
            return True
        return int(bars[-1]["open_time"]) >= expected_latest_daily_open_time(self._now_ms())

    def latest_status(self, symbol: str, timeframe: str) -> dict:
        return dict(self._latest_status.get((symbol, timeframe), {}))

    def _set_latest_status(self, symbol: str, timeframe: str, bars: list[dict], *, refresh_failed: bool = False, message: str | None = None) -> None:
        latest_time = int(bars[-1]["open_time"]) if bars else None
        expected_time = expected_latest_daily_open_time(self._now_ms()) if timeframe == "1d" else None
        self._latest_status[(symbol, timeframe)] = {
            "stale": not self._is_latest_fresh(timeframe, bars),
            "refresh_failed": refresh_failed,
            "latest_time": latest_time,
            "expected_time": expected_time,
            "message": message,
        }

    def _get_latest_cache(self, symbol: str, timeframe: str, limit: int) -> list[dict] | None:
        key = (symbol, timeframe)
        cached = self._latest_cache.get(key)
        if cached is None:
            return None
        cached_at, requested_limit, bars = cached
        if time.monotonic() - cached_at > _LATEST_CACHE_TTL.get(timeframe, 30.0) or requested_limit < limit:
            self._latest_cache.pop(key, None)
            return None
        self._latest_cache.move_to_end(key)
        return bars[-limit:]

    def _set_latest_cache(self, symbol: str, timeframe: str, requested_limit: int, bars: list[dict]) -> None:
        key = (symbol, timeframe)
        self._latest_cache[key] = (time.monotonic(), requested_limit, list(bars))
        self._latest_cache.move_to_end(key)
        while len(self._latest_cache) > _LATEST_CACHE_MAX_ENTRIES:
            self._latest_cache.popitem(last=False)

    @staticmethod
    def _needs_chip_enrichment(symbol: str, timeframe: str, bars: list[dict]) -> bool:
        return (
            bool(symbol)
            and symbol[0].isdigit()
            and timeframe == "1d"
            and bool(bars)
            and any(
                item.get("turnover_rate") is None
                or item.get("circulating_shares") is None
                or item.get("adjustment_factor") is None
                for item in bars
            )
        )

    def _schedule_chip_enrichment(self, symbol: str, timeframe: str, limit: int) -> None:
        key = (symbol, timeframe)
        existing = self._enrichment_tasks.get(key)
        if existing and not existing.done():
            return

        async def enrich() -> None:
            try:
                source = self._source(symbol)
                logger.info("enriching chip fields for %s %s in background", symbol, timeframe)
                fetched = await source.fetch_klines(symbol, timeframe, limit=limit)
                if fetched:
                    await self._store_call("upsert", symbol, timeframe, fetched)
                    complete = await self._store_call("fetch_latest", symbol, timeframe, limit)
                    self._set_latest_cache(symbol, timeframe, limit, complete)
            except Exception:
                logger.warning("chip field enrichment failed for %s %s", symbol, timeframe, exc_info=True)
            finally:
                self._enrichment_tasks.pop(key, None)

        self._enrichment_tasks[key] = asyncio.create_task(enrich())

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
        if not force_refresh:
            cached = self._get_latest_cache(symbol, timeframe, limit)
            if cached is not None:
                logger.info("market memory cache HIT %s %s (%s bars)", symbol, timeframe, len(cached))
                return cached, True

        stored = await self._store_call("fetch_latest", symbol, timeframe, limit)
        stored_fresh = self._is_latest_fresh(timeframe, stored)
        if len(stored) >= limit and stored_fresh and not force_refresh:
            if self._needs_chip_enrichment(symbol, timeframe, stored):
                self._schedule_chip_enrichment(symbol, timeframe, limit)
            result = stored[-limit:]
            self._set_latest_cache(symbol, timeframe, limit, result)
            self._set_latest_status(symbol, timeframe, result)
            return result, True

        source = self._source(symbol)
        try:
            if stored and timeframe == "1d" and not stored_fresh:
                gap_start = int(stored[-1]["open_time"]) + 1
                gap_end = expected_latest_daily_open_time(self._now_ms())
                logger.info(
                    "latest market data stale %s %s [%s -> %s], filling tail from %s",
                    symbol, timeframe, stored[-1]["open_time"], gap_end, source.name,
                )
                fetched = await source.fetch_klines(
                    symbol, timeframe, start_time=gap_start, end_time=gap_end,
                    limit=self._range_limit(timeframe, TimeRange(gap_start, gap_end)),
                ) if gap_start <= gap_end else []
            else:
                fetched = await source.fetch_klines(symbol, timeframe, limit=limit)
        except Exception as error:
            if stored:
                logger.warning(
                    "market API unavailable for %s %s; returning %s stored bars",
                    symbol, timeframe, len(stored), exc_info=True,
                )
                result = stored[-limit:]
                self._set_latest_cache(symbol, timeframe, limit, result)
                self._set_latest_status(
                    symbol, timeframe, result, refresh_failed=True,
                    message=f"{source.name} 更新失败：{error}",
                )
                return result, True
            raise
        await self._store_call("upsert", symbol, timeframe, fetched)
        if fetched:
            await self._store_call(
                "add_coverage", symbol, timeframe,
                min(int(bar["open_time"]) for bar in fetched),
                max(int(bar["open_time"]) for bar in fetched),
            )
        complete = await self._store_call("fetch_latest", symbol, timeframe, limit)
        result = complete[-limit:]
        self._set_latest_cache(symbol, timeframe, limit, result)
        self._set_latest_status(
            symbol, timeframe, result,
            message=None if self._is_latest_fresh(timeframe, result) else f"{source.name} 暂无更新数据",
        )
        return result, False

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
