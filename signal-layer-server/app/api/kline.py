from __future__ import annotations

import logging
from typing import Optional
from fastapi import APIRouter, Query, HTTPException, Depends
from app.api.deps import get_data_service
from app.api.security import require_permission
from app.schemas.kline import KlineResponse, KlineItem

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/klines", tags=["klines"])


@router.get("/{symbol}", response_model=KlineResponse)
async def get_klines(
    symbol: str,
    timeframe: str = Query(default="15m", description="Kline timeframe"),
    limit: int = Query(default=200, ge=1, le=10000),
    force_refresh: bool = Query(default=False),
    start_time: Optional[int] = Query(default=None, description="Range start, Unix milliseconds"),
    end_time: Optional[int] = Query(default=None, description="Range end, Unix milliseconds"),
):
    logger.info(
        f"GET /klines/{symbol} tf={timeframe} limit={limit} "
        f"start={start_time} end={end_time} force_refresh={force_refresh}"
    )
    if (start_time is None) != (end_time is None):
        raise HTTPException(status_code=422, detail="start_time and end_time must be provided together")
    if start_time is not None and end_time is not None and start_time > end_time:
        raise HTTPException(status_code=422, detail="start_time must be less than or equal to end_time")

    ds = get_data_service()
    try:
        result = await ds.fetch_klines(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
            force_refresh=force_refresh,
            start_time=start_time,
            end_time=end_time,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        logger.error(f"GET /klines/{symbol} failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    items = [
        KlineItem(
            open_time=k["open_time"],
            open=str(k["open"]),
            high=str(k["high"]),
            low=str(k["low"]),
            close=str(k["close"]),
            volume=str(k["volume"]),
            amount=str(k.get("amount", 0)),
            turnover=str(k.get("turnover", 0)),
            turnover_rate=str(k["turnover_rate"]) if k.get("turnover_rate") is not None else None,
            circulating_shares=str(k["circulating_shares"]) if k.get("circulating_shares") is not None else None,
            adjustment_factor=str(k["adjustment_factor"]) if k.get("adjustment_factor") is not None else None,
            adjustment_type=k.get("adjustment_type"),
            is_closed=k.get("is_closed", True),
        )
        for k in result["data"]
    ]

    data_count = result["count"]
    logger.info(f"GET /klines/{symbol} -> {data_count} candles (cached={result.get('cached', False)})")
    return KlineResponse(
        symbol=result["symbol"],
        timeframe=result["timeframe"],
        data=items,
        from_time=result.get("from_time"),
        to_time=result.get("to_time"),
        count=data_count,
        cached=result.get("cached", False),
    )
