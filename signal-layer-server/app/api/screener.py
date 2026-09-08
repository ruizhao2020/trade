from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from app.api.deps import (
    get_chan_service,
    get_condition_service,
    get_data_service,
    get_indicator_service,
)
from app.api.symbol import get_symbol_items
from app.schemas.screener import ScreenerMatch, ScreenerRequest, ScreenerResponse
from app.services.signal_evaluation_service import evaluate_template_for_symbol

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/screener", tags=["screener"])


@router.post("/run", response_model=ScreenerResponse)
async def run_screener(request: ScreenerRequest):
    """用同一策略批量评估标的，并按完成度返回匹配结果。"""
    try:
        symbols, universe_total = await get_symbol_items(
            request.market,
            request.keyword,
            request.limit,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        logger.error("Screener symbol loading failed: %s", error, exc_info=True)
        raise HTTPException(status_code=500, detail=f"标的列表加载失败: {error}") from error

    data_service = get_data_service()
    chan_service = get_chan_service()
    indicator_service = get_indicator_service()
    condition_service = get_condition_service()
    semaphore = asyncio.Semaphore(request.concurrency)
    failed_count = 0

    async def evaluate_item(item: dict) -> ScreenerMatch | None:
        nonlocal failed_count
        async with semaphore:
            try:
                signal = await evaluate_template_for_symbol(
                    item["symbol"],
                    request.template,
                    data_service,
                    chan_service,
                    indicator_service,
                    condition_service,
                    kline_limit=request.kline_limit,
                )
            except Exception as error:
                failed_count += 1
                logger.warning("Screener evaluation failed for %s: %s", item.get("symbol"), error)
                return None
            if signal.progress_percent < request.min_progress:
                return None
            return ScreenerMatch(
                symbol=item["symbol"],
                name=item.get("name", item["symbol"]),
                market=item.get("market", request.market),
                industry=item.get("industry"),
                exchange=item.get("exchange"),
                state=signal.state,
                is_ready=signal.is_ready,
                progress_percent=signal.progress_percent,
            )

    evaluated = await asyncio.gather(*(evaluate_item(item) for item in symbols))
    matches = [item for item in evaluated if item is not None]
    matches.sort(key=lambda item: (not item.is_ready, -item.progress_percent, item.symbol))
    return ScreenerResponse(
        market=request.market,
        universe_total=universe_total,
        scanned_count=len(symbols),
        matched_count=len(matches),
        failed_count=failed_count,
        results=matches,
    )
