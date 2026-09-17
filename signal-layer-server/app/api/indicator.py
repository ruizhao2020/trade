import logging
from fastapi import APIRouter, HTTPException, Depends, Request
from app.api.security import optional_user, require_permission
from app.api.deps import get_data_service, get_indicator_service
from app.db import get_session
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.public_site_service import ensure_public_indicator, public_indicator_feature_map, public_indicator_map
from app.services.auth_service import permission_codes
from app.schemas.indicator import (
    IndicatorCalculateRequest, IndicatorCalculateResponse,
    IndicatorResultItem, IndicatorInfo, IndicatorListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/indicator", tags=["indicator"])


# 指标元信息(前端指标库展示用)
INDICATOR_META: dict[str, dict] = {
    "ma": {"name": "移动平均线", "description": "趋势跟踪指标", "default_params": {"period": 5}},
    "macd": {"name": "MACD", "description": "指数平滑异同移动平均线", "default_params": {"fast": 12, "slow": 26, "signal": 9}},
    "kdj": {"name": "KDJ", "description": "随机指标", "default_params": {"n": 9, "m1": 3, "m2": 3}},
    "rsi": {"name": "RSI", "description": "相对强弱指标", "default_params": {"period": 14}},
    "bollinger": {"name": "布林带", "description": "Bollinger Bands 通道指标", "default_params": {"period": 20, "std": 2.0}},
    "liquidity_sweep": {"name": "流动性扫荡反转", "description": "基于流动性扫荡+回收的买卖信号指标。识别摆动高低点的止损猎杀,ATR过滤,HTF趋势对齐。", "default_params": {"piv_len": 8, "atr_len": 14}},
    "volume": {
        "name": "成交量",
        "description": "比较当前量柱与前一量柱，识别缩量、增量、倍量、三倍量和多倍量。",
        "default_params": {
            "shrink_max": 0.8,
            "increase_min": 1.2,
            "double_min": 2.0,
            "triple_min": 3.0,
            "multiple_min": 4.0,
        },
    },
    "chip_distribution": {
        "name": "筹码分布",
        "description": "以近500日日线筹码为基准，支持日线、30分钟和5分钟逐K线演进，估算筹码峰、成本区间和获利盘。",
        "default_params": {"bins": 120, "lookback": 500, "min_turnover_days": 20},
    },
}


@router.get("/list", response_model=IndicatorListResponse)
async def list_indicators(request: Request, user = Depends(optional_user), session: AsyncSession = Depends(get_session)):
    """返回所有可用指标的元信息(前端用于展示指标库)"""
    svc = get_indicator_service()
    available = svc.available_indicators
    private_access = user is not None and "private.access" in permission_codes(user)
    is_public = not private_access or request.headers.get("x-signal-surface", "").lower() == "public"
    policies = await public_indicator_map(session)
    indicators: list[IndicatorInfo] = []
    for ind_type in sorted(available):
        meta = INDICATOR_META.get(ind_type, {})
        # 用默认参数算一次,拿到 render 规格返回给前端
        try:
            result = await svc.calculate(
                symbol="__meta__", timeframe="1d",
                indicator_type=ind_type, params=meta.get("default_params", {}),
                klines=[],
            )
            render = result.render
        except Exception:
            render = None
        features = []
        if render:
            features.extend((plot.field, plot.label or plot.field, False) for plot in render.plots)
            features.extend((f"marker:{marker.field}", marker.field, True) for marker in render.markers)
        policy = await ensure_public_indicator(session, ind_type, meta.get("name", ind_type), features)
        policies[ind_type] = policy
        if is_public and not policy.public_visible:
            continue
        if is_public and render:
            feature_map = await public_indicator_feature_map(session, ind_type)
            render = render.model_copy(update={
                "plots": [plot for plot in render.plots if not feature_map or feature_map.get(plot.field) and feature_map[plot.field].public_visible],
                "markers": [marker for marker in render.markers if policy.show_markers and feature_map.get(f"marker:{marker.field}") and feature_map[f"marker:{marker.field}"].public_visible],
            })
        indicators.append(IndicatorInfo(
            type=ind_type,
            name=(policy.display_name if is_public and policy and policy.display_name else meta.get("name", ind_type)),
            description=meta.get("description", "") if not is_public or not policy or policy.show_details else "",
            default_params=meta.get("default_params", {}) if not is_public or not policy or policy.show_parameters else {},
            render=render,
        ))
    await session.commit()
    return IndicatorListResponse(indicators=indicators)


@router.post("/calculate", response_model=IndicatorCalculateResponse)
async def calculate_indicators(req: IndicatorCalculateRequest, request: Request, user = Depends(optional_user), session: AsyncSession = Depends(get_session)):
    logger.info(f"POST /indicator/calculate symbol={req.symbol} tf={req.timeframe} "
                f"indicators={[i.type for i in req.indicators]}")
    private_access = user is not None and "private.access" in permission_codes(user)
    public_surface = not private_access or request.headers.get("x-signal-surface", "").lower() == "public"
    policies = await public_indicator_map(session) if public_surface else {}
    if public_surface and any(not policies.get(item.type) or not policies[item.type].public_visible for item in req.indicators):
        raise HTTPException(status_code=403, detail="该指标仅在受限研究工作区提供")
    ds = get_data_service()
    requires_chip_data = any(ind.type == "chip_distribution" for ind in req.indicators)
    if requires_chip_data and (
        req.timeframe not in {"1d", "30m", "5m"}
        or not req.symbol
        or not req.symbol[0].isdigit()
    ):
        raise HTTPException(status_code=400, detail="筹码分布目前仅支持股票的日线、30分钟和5分钟")
    fetch_limit = min(req.kline_limit + 100, 1000) if requires_chip_data and req.timeframe != "1d" else req.kline_limit
    indicator_context: dict = {}
    try:
        kline_result = await ds.fetch_klines(
            symbol=req.symbol, timeframe=req.timeframe, limit=fetch_limit,
        )
        if requires_chip_data and req.timeframe == "1d" and any(
            bar.get("turnover_rate") is None
            or bar.get("circulating_shares") is None
            or bar.get("adjustment_factor") is None
            for bar in kline_result["data"]
        ):
            logger.info("chip fields incomplete for %s, refreshing before calculation", req.symbol)
            kline_result = await ds.fetch_klines(
                symbol=req.symbol,
                timeframe=req.timeframe,
                limit=req.kline_limit,
                force_refresh=True,
            )
        if requires_chip_data and req.timeframe != "1d":
            lookback = max(
                int(ind.params.get("lookback", 500))
                for ind in req.indicators
                if ind.type == "chip_distribution"
            )
            daily_result = await ds.fetch_klines(
                symbol=req.symbol,
                timeframe="1d",
                limit=min(max(lookback, 500), 1000),
            )
            if any(
                bar.get("turnover_rate") is None
                or bar.get("circulating_shares") is None
                or bar.get("adjustment_factor") is None
                for bar in daily_result["data"]
            ):
                daily_result = await ds.fetch_klines(
                    symbol=req.symbol,
                    timeframe="1d",
                    limit=min(max(lookback, 500), 1000),
                    force_refresh=True,
                )
            indicator_context["daily_klines"] = daily_result["data"]
    except Exception as e:
        logger.error(f"POST /indicator/calculate kline fetch failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    klines = kline_result["data"]

    svc = get_indicator_service()
    results: list[IndicatorResultItem] = []

    for ind in req.indicators:
        try:
            result = await svc.calculate(
                symbol=req.symbol,
                timeframe=req.timeframe,
                indicator_type=ind.type,
                params=ind.params,
                klines=klines,
                context=indicator_context if ind.type == "chip_distribution" else None,
            )
            policy = policies.get(ind.type)
            public_render = result.render
            public_values = result.values
            if public_surface and result.render and policy:
                feature_map = await public_indicator_feature_map(session, ind.type)
                public_plots = [plot for plot in result.render.plots if not feature_map or feature_map.get(plot.field) and feature_map[plot.field].public_visible]
                public_markers = [marker for marker in result.render.markers if policy.show_markers and feature_map.get(f"marker:{marker.field}") and feature_map[f"marker:{marker.field}"].public_visible]
                public_render = result.render.model_copy(update={"plots": public_plots, "markers": public_markers})
                if not policy.show_details:
                    allowed_fields = {"time", *(plot.field for plot in public_plots), *(marker.field for marker in public_markers)}
                    public_values = [{key: value for key, value in row.items() if key in allowed_fields} for row in result.values]
            results.append(IndicatorResultItem(
                type=result.type,
                params=result.params,
                values=public_values,
                render=public_render,
                profile_data=result.profile_data,
                cached=False,
            ))
            logger.info(f"  {ind.type} calculated -> {len(result.values)} values")
        except ValueError as e:
            logger.error(f"POST /indicator/calculate invalid params for {ind.type}: {e}", exc_info=True)
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"POST /indicator/calculate {ind.type} failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    logger.info(f"POST /indicator/calculate -> {len(results)} indicators computed")
    return IndicatorCalculateResponse(
        symbol=req.symbol,
        timeframe=req.timeframe,
        results=results,
    )
