import logging
from fastapi import APIRouter, HTTPException
from app.api.deps import get_data_service, get_indicator_service
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
}


@router.get("/list", response_model=IndicatorListResponse)
async def list_indicators():
    """返回所有可用指标的元信息(前端用于展示指标库)"""
    svc = get_indicator_service()
    available = svc.available_indicators
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
        indicators.append(IndicatorInfo(
            type=ind_type,
            name=meta.get("name", ind_type),
            description=meta.get("description", ""),
            default_params=meta.get("default_params", {}),
            render=render,
        ))
    return IndicatorListResponse(indicators=indicators)


@router.post("/calculate", response_model=IndicatorCalculateResponse)
async def calculate_indicators(req: IndicatorCalculateRequest):
    logger.info(f"POST /indicator/calculate symbol={req.symbol} tf={req.timeframe} "
                f"indicators={[i.type for i in req.indicators]}")
    ds = get_data_service()
    try:
        kline_result = await ds.fetch_klines(
            symbol=req.symbol, timeframe=req.timeframe, limit=req.kline_limit,
        )
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
            )
            results.append(IndicatorResultItem(
                type=result.type,
                params=result.params,
                values=result.values,
                render=result.render,
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
