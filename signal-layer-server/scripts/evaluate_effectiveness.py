"""按股票池跑指标有效性评测，把结论写入 indicator_effectiveness。

用法（在 signal-layer-server 下）：
    PYTHONPATH=. python scripts/evaluate_effectiveness.py
    PYTHONPATH=. python scripts/evaluate_effectiveness.py --symbols 40 --bars 800
    PYTHONPATH=. python scripts/evaluate_effectiveness.py --indicators volume_price,macd
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from app.cache.indicator_cache import IndicatorCache
import app.db as db
from app.services.data_service import DataService
from app.services.effectiveness_service import EffectivenessService
from app.services.indicator_service import IndicatorService


def load_symbols(limit: int) -> list[str]:
    """从 stock_info 取前 N 个代码，转成 000001_sz 形式。"""
    from app.api.symbol import _fetch_stock_symbols

    rows, _ = _fetch_stock_symbols(None, limit, 0)
    return [row["symbol"] for row in rows]


async def run(args) -> None:
    await db.init_db()
    symbols = load_symbols(args.symbols)
    print(f"universe={args.universe} symbols={len(symbols)} timeframe={args.timeframe} bars={args.bars}")
    service = EffectivenessService(DataService(), IndicatorService(IndicatorCache(None)))
    indicator_types = [name for name in args.indicators.split(",") if name] if args.indicators else None
    async with db._session_factory() as session:
        rows = await service.evaluate(
            session,
            symbols,
            timeframe=args.timeframe,
            limit=args.bars,
            universe=args.universe,
            indicator_types=indicator_types,
        )
        await session.commit()
    print(f"saved {len(rows)} effectiveness rows")
    for row in sorted(rows, key=lambda item: (item.verdict != "valid", -abs(item.excess_return or 0)))[:40]:
        print(
            f"{row.verdict:12s} {row.indicator_type}:{row.field} ({row.direction}) "
            f"N={row.sample_n} 超额={row.excess_return} p={row.p_value}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="指标有效性评测")
    parser.add_argument("--symbols", type=int, default=30, help="股票池标的数量")
    parser.add_argument("--timeframe", default="1d", help="周期，默认 1d")
    parser.add_argument("--bars", type=int, default=800, help="每个标的取的 K 线根数")
    parser.add_argument("--universe", default="stock", help="股票池名称（写入结论作用域）")
    parser.add_argument("--indicators", default="", help="逗号分隔的指标类型；默认全部")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
