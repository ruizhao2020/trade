import asyncio

from app.market_data.manager import MarketDataManager
from app.market_data.ranges import TimeRange, merge_ranges


def bar(open_time: int) -> dict:
    return {
        "open_time": open_time,
        "open": 10.0,
        "close": 10.1,
        "high": 10.2,
        "low": 9.9,
        "volume": 100.0,
        "is_closed": True,
    }


class MemoryStore:
    def __init__(self):
        self.bars: dict[tuple[str, str], dict[int, dict]] = {}
        self.covered: dict[tuple[str, str], list[TimeRange]] = {}

    def fetch_latest(self, symbol, timeframe, limit):
        values = sorted(self.bars.get((symbol, timeframe), {}).values(), key=lambda item: item["open_time"])
        return values[-limit:]

    def fetch_range(self, symbol, timeframe, start_time, end_time):
        return [
            item for item in self.fetch_latest(symbol, timeframe, 100_000)
            if start_time <= item["open_time"] <= end_time
        ]

    def upsert(self, symbol, timeframe, bars):
        target = self.bars.setdefault((symbol, timeframe), {})
        for item in bars:
            target[item["open_time"]] = item

    def coverage(self, symbol, timeframe):
        return [(item.start, item.end) for item in self.covered.get((symbol, timeframe), [])]

    def add_coverage(self, symbol, timeframe, start_time, end_time):
        key = (symbol, timeframe)
        self.covered[key] = merge_ranges([
            *self.covered.get(key, []),
            TimeRange(start_time, end_time),
        ])


class RangeSource:
    name = "test-api"
    range_authoritative = True

    def __init__(self):
        self.calls: list[tuple[int | None, int | None]] = []

    async def fetch_klines(self, symbol, timeframe, start_time=None, end_time=None, limit=500):
        self.calls.append((start_time, end_time))
        if start_time is None or end_time is None:
            return [bar(index) for index in range(limit)]
        return [bar(index) for index in range(start_time, end_time + 1)]

    async def subscribe_klines(self, symbol, timeframe, callback):
        async def noop():
            return None
        return noop


class FailingSource(RangeSource):
    async def fetch_klines(self, symbol, timeframe, start_time=None, end_time=None, limit=500):
        raise RuntimeError("行情源暂时不可用")


def test_manager_fetches_only_the_missing_range_and_then_uses_db():
    store = MemoryStore()
    source = RangeSource()
    manager = MarketDataManager(store, source, source)

    async def scenario():
        await manager.fetch("000001_sz", "1d", start_time=3, end_time=5)
        await manager.fetch("000001_sz", "1d", start_time=7, end_time=8)
        complete_result = await manager.fetch("000001_sz", "1d", start_time=5, end_time=8)
        repeated_result = await manager.fetch("000001_sz", "1d", start_time=5, end_time=8)
        return complete_result, repeated_result

    (complete, cached), (repeated, repeated_cached) = asyncio.run(scenario())

    assert source.calls == [(3, 5), (7, 8), (6, 6)]
    assert [item["open_time"] for item in complete] == [5, 6, 7, 8]
    assert cached is False

    assert source.calls == [(3, 5), (7, 8), (6, 6)]
    assert [item["open_time"] for item in repeated] == [5, 6, 7, 8]
    assert repeated_cached is True


def test_latest_request_does_not_call_api_when_db_has_enough_rows():
    store = MemoryStore()
    source = RangeSource()
    store.upsert("000001_sz", "5m", [bar(index) for index in range(10)])
    manager = MarketDataManager(store, source, source)

    values, cached = asyncio.run(manager.fetch("000001_sz", "5m", limit=5))

    assert [item["open_time"] for item in values] == [5, 6, 7, 8, 9]
    assert source.calls == []
    assert cached is True


def test_latest_memory_cache_reuses_data_across_kline_and_analysis_requests():
    store = MemoryStore()
    source = RangeSource()
    manager = MarketDataManager(store, source, source)

    first, first_cached = asyncio.run(manager.fetch("000001_sz", "1d", limit=5))
    second, second_cached = asyncio.run(manager.fetch("000001_sz", "1d", limit=5))

    assert [item["open_time"] for item in first] == [0, 1, 2, 3, 4]
    assert second == first
    assert source.calls == [(None, None)]
    assert first_cached is False
    assert second_cached is True


def test_latest_request_returns_stored_rows_when_api_is_unavailable():
    store = MemoryStore()
    source = FailingSource()
    store.upsert("000001_sz", "1d", [bar(index) for index in range(3)])
    manager = MarketDataManager(store, source, source)

    values, cached = asyncio.run(manager.fetch("000001_sz", "1d", limit=5))

    assert [item["open_time"] for item in values] == [0, 1, 2]
    assert cached is True


def test_concurrent_requests_for_same_symbol_share_one_gap_fill():
    store = MemoryStore()
    source = RangeSource()
    manager = MarketDataManager(store, source, source)

    async def scenario():
        return await asyncio.gather(
            manager.fetch("000001_sz", "1d", start_time=3, end_time=5),
            manager.fetch("000001_sz", "1d", start_time=3, end_time=5),
        )

    first, second = asyncio.run(scenario())
    assert source.calls == [(3, 5)]
    assert first[1] is False
    assert second[1] is True
