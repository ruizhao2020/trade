import asyncio

from app.cache.indicator_cache import IndicatorCache
from app.services.indicator_service import IndicatorService


def _klines(count: int):
    return [
        {
            "open_time": 1_700_000_000_000 + index * 86_400_000,
            "open": 10 + index,
            "high": 11 + index,
            "low": 9 + index,
            "close": 10.5 + index,
            "volume": 100 + index,
        }
        for index in range(count)
    ]


def test_short_indicator_cache_does_not_serve_longer_history():
    async def run():
        service = IndicatorService(IndicatorCache(None))
        full = _klines(500)
        short = full[-200:]
        short_result = await service.calculate("000001_sz", "1d", "ma", {"period": 5}, short)
        long_result = await service.calculate("000001_sz", "1d", "ma", {"period": 5}, full)
        assert len(short_result.values) == 200
        assert len(long_result.values) == 500
        assert int(long_result.values[0]["time"]) == full[0]["open_time"]

    asyncio.run(run())


def test_long_indicator_cache_is_cropped_for_shorter_request():
    async def run():
        service = IndicatorService(IndicatorCache(None))
        full = _klines(500)
        short = full[-200:]
        await service.calculate("000001_sz", "1d", "ma", {"period": 10}, full)
        short_result = await service.calculate("000001_sz", "1d", "ma", {"period": 10}, short)
        assert len(short_result.values) == 200
        assert int(short_result.values[0]["time"]) == short[0]["open_time"]
        assert int(short_result.values[-1]["time"]) == short[-1]["open_time"]

    asyncio.run(run())
