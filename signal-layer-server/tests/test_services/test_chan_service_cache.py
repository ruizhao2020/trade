import asyncio
import math

from app.cache.indicator_cache import IndicatorCache, key_chan
from app.services.chan_service import ChanService


def _klines(count: int):
    """构造一段有明显波动的日线，保证引擎能构建出笔。"""
    bars = []
    for index in range(count):
        base = 5000 + 400 * math.sin(index / 9) + 120 * math.sin(index / 3)
        bars.append({
            "open_time": 1_700_000_000_000 + index * 86_400_000,
            "open": base,
            "high": base + 30,
            "low": base - 30,
            "close": base + 10,
            "volume": 100 + index,
        })
    return bars


def test_short_chan_cache_does_not_serve_longer_history():
    """先算短区间，再请求长区间时必须重算，否则缠论只覆盖图表后半段。"""

    async def run():
        service = ChanService(IndicatorCache(None))
        full = _klines(500)
        short = full[-200:]

        short_result = await service.analyze("V0", "1d", short)
        long_result = await service.analyze("V0", "1d", full)

        assert len(long_result.bis) > len(short_result.bis)
        assert long_result.bis[0].start_time <= short_result.bis[0].start_time

    asyncio.run(run())


def test_chan_cache_covers_identical_window():
    """区间完全一致时仍应命中缓存，避免每次请求都重算。"""

    async def run():
        cache = IndicatorCache(None)
        service = ChanService(cache)
        full = _klines(500)

        first = await service.analyze("V0", "1d", full)
        cached = await cache.get(key_chan("V0", "1d", 0.7, window=len(full)))

        assert cached is not None
        assert cached["data_start_time"] == full[0]["open_time"]
        assert cached["data_count"] == len(full)

        second = await service.analyze("V0", "1d", full)
        assert len(second.bis) == len(first.bis)

    asyncio.run(run())


def test_chan_cache_keeps_windows_separate():
    """选股(短窗口)与图表(长窗口)必须各得其所，结果不能取决于谁先写入。"""

    async def run():
        service = ChanService(IndicatorCache(None))
        full = _klines(500)
        short = full[-200:]

        # 先长后短：短窗口请求不能被长窗口缓存"顶替"
        await service.analyze("V0", "1d", full)
        short_result = await service.analyze("V0", "1d", short)
        # 反过来再算一次，两个顺序必须得到一致结果
        short_again = await service.analyze("V0", "1d", short)
        long_result = await service.analyze("V0", "1d", full)

        assert len(short_result.bis) == len(short_again.bis)
        assert len(long_result.bis) > len(short_result.bis)
        assert short_result.bis[0].start_time >= short[0]["open_time"]

    asyncio.run(run())


def test_chan_cache_invalidates_when_history_is_backfilled():
    """同一终点但历史被补齐（起点前移）时不能复用旧结果。"""

    async def run():
        service = ChanService(IndicatorCache(None))
        full = _klines(500)

        await service.analyze("V0", "1d", full[-200:])
        backfilled = await service.analyze("V0", "1d", full)

        assert backfilled.bis[0].start_time <= full[-200:][0]["open_time"]

    asyncio.run(run())
