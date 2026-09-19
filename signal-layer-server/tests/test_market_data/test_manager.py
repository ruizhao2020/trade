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
        "turnover_rate": 1.0,
        "circulating_shares": 10_000.0,
        "adjustment_factor": 1.0,
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


class EmptySource(RangeSource):
    async def fetch_klines(self, symbol, timeframe, start_time=None, end_time=None, limit=500):
        self.calls.append((start_time, end_time))
        return []


class TailSource(RangeSource):
    def __init__(self, latest_time):
        super().__init__()
        self.latest_time = latest_time

    async def fetch_klines(self, symbol, timeframe, start_time=None, end_time=None, limit=500):
        self.calls.append((start_time, end_time))
        return [bar(self.latest_time)]


class SlowSource(RangeSource):
    async def fetch_klines(self, symbol, timeframe, start_time=None, end_time=None, limit=500):
        await asyncio.sleep(0.01)
        return await super().fetch_klines(symbol, timeframe, start_time, end_time, limit)


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


def test_latest_request_checks_source_even_when_db_has_enough_rows():
    store = MemoryStore()
    store.upsert("000001_sz", "5m", [bar(index) for index in range(5)])
    source = RangeSource()
    manager = MarketDataManager(store, source, source)

    values, cached = asyncio.run(manager.fetch("000001_sz", "5m", limit=5))

    assert [item["open_time"] for item in values] == [0, 1, 2, 3, 4]
    assert source.calls == [(None, None)]
    assert cached is False
    assert manager.latest_status("000001_sz", "5m")["stale"] is False


def test_latest_request_upserts_new_bar_returned_by_source():
    store = MemoryStore()
    store.upsert("000001_sz", "5m", [bar(index) for index in range(1, 6)])
    source = TailSource(6)
    manager = MarketDataManager(store, source, source)

    values, cached = asyncio.run(manager.fetch("000001_sz", "5m", limit=5))

    assert [item["open_time"] for item in values] == [2, 3, 4, 5, 6]
    assert source.calls == [(None, None)]
    assert cached is False


def test_long_holiday_is_confirmed_by_source_instead_of_calendar_guess():
    store = MemoryStore()
    last_trading_day = 1_800_000_000_000
    day = 86_400_000
    store.upsert("000001_sz", "1d", [bar(last_trading_day - day * index) for index in range(4, -1, -1)])
    source = TailSource(last_trading_day)
    manager = MarketDataManager(store, source, source)

    values, cached = asyncio.run(manager.fetch("000001_sz", "1d", limit=5))

    assert values[-1]["open_time"] == last_trading_day
    assert source.calls == [(None, None)]
    assert cached is False
    assert manager.latest_status("000001_sz", "1d") == {
        "stale": False,
        "refresh_failed": False,
        "latest_time": last_trading_day,
        "expected_time": None,
        "message": None,
    }


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
    status = manager.latest_status("000001_sz", "1d")
    assert status["stale"] is True
    assert status["refresh_failed"] is True
    assert status["expected_time"] is None


def test_latest_daily_refreshes_tail_even_when_db_has_enough_rows():
    store = MemoryStore()
    store.upsert("RB0", "1d", [bar(index) for index in range(5)])
    source = TailSource(5)
    manager = MarketDataManager(store, source, source)

    values, cached = asyncio.run(manager.fetch("RB0", "1d", limit=5))

    assert values[-1]["open_time"] == 5
    assert source.calls == [(None, None)]
    assert cached is False
    assert manager.latest_status("RB0", "1d")["stale"] is False


def test_successful_empty_response_confirms_no_update():
    store = MemoryStore()
    store.upsert("RB0", "1d", [bar(index) for index in range(5)])
    source = EmptySource()
    manager = MarketDataManager(store, source, source)

    values, cached = asyncio.run(manager.fetch("RB0", "1d", limit=5))

    assert values[-1]["open_time"] == 4
    assert cached is False
    status = manager.latest_status("RB0", "1d")
    assert status["stale"] is False
    assert status["message"] == "test-api 已确认暂无更新数据"


def test_latest_confirmation_ttl_avoids_repeated_api_calls_and_expires():
    clock = [100.0]
    store = MemoryStore()
    store.upsert("RB0", "1d", [bar(index) for index in range(5)])
    source = RangeSource()
    manager = MarketDataManager(store, source, source, monotonic_clock=lambda: clock[0])

    async def scenario():
        first = await manager.fetch("RB0", "1d", limit=5)
        clock[0] += 299
        second = await manager.fetch("RB0", "1d", limit=5)
        clock[0] += 2
        third = await manager.fetch("RB0", "1d", limit=5)
        return first, second, third

    first, second, third = asyncio.run(scenario())

    assert source.calls == [(None, None), (None, None)]
    assert first[1] is False
    assert second[1] is True
    assert third[1] is False


def test_force_refresh_bypasses_confirmation_ttl():
    store = MemoryStore()
    source = RangeSource()
    manager = MarketDataManager(store, source, source)

    async def scenario():
        await manager.fetch("RB0", "1d", limit=5)
        await manager.fetch("RB0", "1d", limit=5, force_refresh=True)

    asyncio.run(scenario())

    assert source.calls == [(None, None), (None, None)]


def test_concurrent_latest_requests_share_one_source_confirmation():
    store = MemoryStore()
    source = SlowSource()
    manager = MarketDataManager(store, source, source)

    async def scenario():
        return await asyncio.gather(
            manager.fetch("RB0", "1d", limit=5),
            manager.fetch("RB0", "1d", limit=5),
        )

    first, second = asyncio.run(scenario())

    assert source.calls == [(None, None)]
    assert first[1] is False
    assert second[1] is True


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
