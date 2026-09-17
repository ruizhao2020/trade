import logging
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from app.api.security import optional_user, require_permission
from app.services.auth_service import permission_codes
from app.api.deps import get_data_service, get_chan_service
from app.db import get_session
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.public_site_service import public_indicator_feature_map, public_indicator_map
from app.schemas.chan import (
    ChanAnalysisResponse, BiSchema, DuanSchema,
    ZhongshuSchema, BuySellPointSchema, DivergenceSchema,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/chan", tags=["chan"])


@router.get("/{symbol}/{timeframe}", response_model=ChanAnalysisResponse)
async def get_chan_analysis(
    request: Request,
    symbol: str,
    timeframe: str,
    limit: int = Query(default=200, ge=10, le=500),
    user = Depends(optional_user),
    session: AsyncSession = Depends(get_session),
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
            bi_indices=z.bi_indices, break_direction=z.break_direction,
        )
        for z in result.zhongshus
    ]

    duan_zhongshus = [
        ZhongshuSchema(
            index=z.index,
            high=str(z.high), low=str(z.low), mid=str(z.mid),
            start_time=z.start_time, end_time=z.end_time,
            level=z.level, broken=z.broken,
            bi_indices=z.bi_indices, break_direction=z.break_direction,
        )
        for z in result.duan_zhongshus
    ]

    points = [
        BuySellPointSchema(
            type=p.type, price=str(p.price), time=p.time,
            confirmed=p.confirmed, strength=p.strength,
            zhongshu_index=p.zhongshu_index, bi_index=p.bi_index,
            reason=p.reason, divergence_index=p.divergence_index,
        )
        for p in result.buy_sell_points
    ]
    divergences = [
        DivergenceSchema(
            index=item.index, type=item.type, level=item.level, kind=item.kind,
            price=str(item.price), time=item.time,
            zhongshu_index=item.zhongshu_index,
            reference_bi_index=item.reference_bi_index,
            current_bi_index=item.current_bi_index,
            reference_power=item.reference_power,
            current_power=item.current_power,
            strength_ratio=item.strength_ratio,
            confirmed=item.confirmed,
            reasons=item.reasons,
        )
        for item in result.divergences
    ]

    # The public build receives structural Chan data only. Action-oriented
    # signals and divergence reasons are available exclusively to the private
    # surface; this is enforced at the API response layer, not just in React.
    private_access = user is not None and "private.access" in permission_codes(user)
    if not private_access or request.headers.get("x-signal-surface", "").lower() == "public":
        indicator_policies = await public_indicator_map(session)
        policies = await public_indicator_feature_map(session, "chan")
        chan_policy = indicator_policies.get("chan")
        if not chan_policy or not chan_policy.public_visible:
            bis, duans, zhongshus, duan_zhongshus, divergences, points = [], [], [], [], [], []
            policies = {}
        if not policies.get("bi") or not policies["bi"].public_visible:
            bis = []
        if not policies.get("duan") or not policies["duan"].public_visible:
            duans = []
        if not policies.get("zhongshu") or not policies["zhongshu"].public_visible:
            zhongshus = []
            duan_zhongshus = []
        divergence_policy = policies.get("divergence")
        if not divergence_policy or not divergence_policy.public_visible:
            divergences = []
        elif not divergence_policy.show_details:
            divergences = [item.model_copy(update={"reasons": []}) for item in divergences]
        point_policy = policies.get("buy_sell_points")
        if not point_policy or not point_policy.public_visible:
            points = []
        elif not point_policy.show_details:
            points = [item.model_copy(update={"reason": None, "divergence_index": None}) for item in points]

    actual_cached = False

    logger.info(f"GET /chan/{symbol}/{timeframe} -> {len(bis)} bis, {len(duans)} duans, "
                f"{len(zhongshus)} bi_zs, {len(duan_zhongshus)} duan_zs, "
                f"{len(divergences)} divergences, {len(points)} points")
    return ChanAnalysisResponse(
        symbol=symbol,
        timeframe=timeframe,
        bis=bis,
        duans=duans,
        zhongshus=zhongshus,
        duan_zhongshus=duan_zhongshus,
        buy_sell_points=points,
        divergences=divergences,
        updated_at=result.updated_at,
        cached=actual_cached,
    )
