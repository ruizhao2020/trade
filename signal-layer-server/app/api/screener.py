from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Depends
from app.api.security import require_permission

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


@router.post("/run", response_model=ScreenerResponse, dependencies=[Depends(require_permission("screener.run"))])
async def run_screener(request: ScreenerRequest):
    """用同一策略批量评估标的，并按完成度返回匹配结果。"""
    try:
        symbols, universe_total = await get_symbol_items(
            request.market,
            request.keyword,
            request.limit,
            request.offset,
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
    failed_count = 0

    async def evaluate_item(item: dict) -> ScreenerMatch | None:
        nonlocal failed_count
        try:
            signal = await evaluate_template_for_symbol(
                item["symbol"], request.template, data_service, chan_service,
                indicator_service, condition_service, kline_limit=request.kline_limit,
            )
        except Exception as error:
            failed_count += 1
            logger.warning("Screener evaluation failed for %s: %s", item.get("symbol"), error)
            return None
        if signal.state not in request.states or signal.progress_percent < request.min_progress:
            return None
        return ScreenerMatch(
            symbol=item["symbol"], name=item.get("name", item["symbol"]),
            market=item.get("market", request.market), industry=item.get("industry"),
            exchange=item.get("exchange"), state=signal.state,
            is_ready=signal.is_ready, progress_percent=signal.progress_percent,
        )

    # 按并发数分批扫描。每批完成后立即检查目标数量，达到后不再发起下一批，
    # 因此最多只会多扫描当前批次中的少量标的。
    matches: list[ScreenerMatch] = []
    scanned_count = 0
    for offset in range(0, len(symbols), request.concurrency):
        batch = symbols[offset:offset + request.concurrency]
        evaluated = await asyncio.gather(*(evaluate_item(item) for item in batch))
        scanned_count += len(batch)
        matches.extend(item for item in evaluated if item is not None)
        if len(matches) >= request.target_count:
            break
    matches.sort(key=lambda item: (not item.is_ready, -item.progress_percent, item.symbol))
    matches = matches[:request.target_count]
    return ScreenerResponse(
        market=request.market,
        universe_total=universe_total,
        scanned_count=scanned_count,
        matched_count=len(matches),
        failed_count=failed_count,
        target_count=request.target_count,
        stopped_early=scanned_count < len(symbols),
        results=matches,
    )
