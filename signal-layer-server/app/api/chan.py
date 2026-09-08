import logging
from fastapi import APIRouter, HTTPException, Query
from app.api.deps import get_data_service, get_chan_service
from app.schemas.chan import (
    ChanAnalysisResponse, BiSchema, DuanSchema,
    ZhongshuSchema, BuySellPointSchema,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/chan", tags=["chan"])


@router.get("/{symbol}/{timeframe}", response_model=ChanAnalysisResponse)
async def get_chan_analysis(
    symbol: str,
    timeframe: str,
    limit: int = Query(default=200, ge=10, le=500),
):
    logger.info(f"GET /chan/{symbol}/{timeframe} limit={limit}")
    ds = get_data_service()
    try:
        kline_result = await ds.fetch_klines(
            symbol=symbol, timeframe=timeframe, limit=limit,
        )
    except Exception as e:
        logger.error(f"GET /chan/{symbol}/{timeframe} kline fetch failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    klines = kline_result["data"]

    cs = get_chan_service()
    try:
        result = await cs.analyze(symbol, timeframe, klines)
    except Exception as e:
        logger.error(f"GET /chan/{symbol}/{timeframe} analysis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chan analysis failed: {e}")

    bis = [
        BiSchema(
            index=b.index, direction=b.direction,
            start_time=b.start_time, end_time=b.end_time,
            start_price=str(b.start_price), end_price=str(b.end_price),
            high=str(b.high), low=str(b.low),
        )
        for b in result.bis
    ]

    duans = [
        DuanSchema(
            index=d.index, direction=d.direction,
            bi_indices=d.bi_indices,
            start_time=d.start_time, end_time=d.end_time,
            start_price=str(d.start_price), end_price=str(d.end_price),
            high=str(d.high), low=str(d.low),
            feat_elements=d.feat_elements,
            merged_feat=d.merged_feat,
            fenxing_type=d.fenxing_type,
        )
        for d in result.duans
    ]

    zhongshus = [
        ZhongshuSchema(
            index=z.index,
            high=str(z.high), low=str(z.low), mid=str(z.mid),
            start_time=z.start_time, end_time=z.end_time,
            level=z.level, broken=z.broken,
        )
        for z in result.zhongshus
    ]

    duan_zhongshus = [
        ZhongshuSchema(
            index=z.index,
            high=str(z.high), low=str(z.low), mid=str(z.mid),
            start_time=z.start_time, end_time=z.end_time,
            level=z.level, broken=z.broken,
        )
        for z in result.duan_zhongshus
    ]

    points = [
        BuySellPointSchema(
            type=p.type, price=str(p.price), time=p.time,
            confirmed=p.confirmed, strength=p.strength,
        )
        for p in result.buy_sell_points
    ]

    actual_cached = False

    logger.info(f"GET /chan/{symbol}/{timeframe} -> {len(bis)} bis, {len(duans)} duans, "
                f"{len(zhongshus)} bi_zs, {len(duan_zhongshus)} duan_zs, {len(points)} points")
    return ChanAnalysisResponse(
        symbol=symbol,
        timeframe=timeframe,
        bis=bis,
        duans=duans,
        zhongshus=zhongshus,
        duan_zhongshus=duan_zhongshus,
        buy_sell_points=points,
        updated_at=result.updated_at,
        cached=actual_cached,
    )
