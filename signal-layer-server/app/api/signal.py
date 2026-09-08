import logging
from fastapi import APIRouter, HTTPException
from app.api.deps import get_data_service, get_chan_service, get_indicator_service, get_condition_service
from app.schemas.signal import (
    EvaluateRequest, SignalResult,
    BacktestRequest, BacktestResult,
)
from app.services.backtest_service import BacktestService
from app.services.signal_evaluation_service import (
    evaluate_template_for_symbol,
    load_template_context,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/signal", tags=["signal"])


@router.post("/evaluate", response_model=SignalResult)
async def evaluate_signal(req: EvaluateRequest):
    template = req.template
    symbol = req.symbol
    logger.info(f"POST /signal/evaluate symbol={symbol} template={template.id} logic={template.logic} "
                f"primary_tf={template.primary_tf}")

    ds = get_data_service()
    cs = get_chan_service()
    ind_svc = get_indicator_service()
    cond_svc = get_condition_service()
    try:
        result = await evaluate_template_for_symbol(
            symbol,
            template,
            ds,
            cs,
            ind_svc,
            cond_svc,
        )
    except Exception as e:
        logger.error(f"POST /signal/evaluate condition evaluation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    logger.info(f"POST /signal/evaluate -> state={result.state} progress={result.progress_percent}% "
                f"is_ready={result.is_ready}")
    return result


@router.post("/backtest", response_model=BacktestResult)
async def backtest(req: BacktestRequest):
    template = req.template
    symbol = req.symbol
    logger.info(f"POST /signal/backtest symbol={symbol} template={template.id} limit={req.kline_limit}")

    ds = get_data_service()
    cs = get_chan_service()
    ind_svc = get_indicator_service()

    # 收集所有条件组（入场 + 条件式出场）
    all_groups = list(template.condition_groups)
    if template.trade_params and template.trade_params.exit_conditions:
        all_groups += template.trade_params.exit_conditions

    try:
        kline_data, chan_data, indicator_data = await load_template_context(
            symbol,
            template,
            ds,
            cs,
            ind_svc,
            groups=all_groups,
            kline_limit=req.kline_limit,
        )
    except Exception as e:
        logger.error(f"POST /signal/backtest data loading failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    bt = BacktestService(get_condition_service())
    try:
        result = await bt.run(symbol, template, kline_data, chan_data, indicator_data, req.kline_limit)
    except Exception as e:
        logger.error(f"POST /signal/backtest failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    logger.info(f"POST /signal/backtest -> {result.total_trades} trades, win_rate={result.win_rate}%")
    return result
