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
    IndicatorResultItem, IndicatorErrorItem, IndicatorInfo, IndicatorListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/indicator", tags=["indicator"])


# 指标元信息(前端指标库展示用)
INDICATOR_META: dict[str, dict] = {
    "ma": {
        "name": "移动平均线",
        "description": "趋势跟踪指标，支持向上、向下、方向反转、支撑和压制判断。",
        "default_params": {"period": 5, "touch_tolerance_pct": 0.5},
    },
    "macd": {"name": "MACD", "description": "指数平滑异同移动平均线", "default_params": {"fast": 12, "slow": 26, "signal": 9}},
    "kdj": {"name": "KDJ", "description": "随机指标", "default_params": {"n": 9, "m1": 3, "m2": 3}},
    "rsi": {"name": "RSI", "description": "相对强弱指标", "default_params": {"period": 14}},
    "bollinger": {"name": "布林带", "description": "Bollinger Bands 通道指标", "default_params": {"period": 20, "std": 2.0}},
    "liquidity_sweep": {"name": "流动性扫荡反转", "description": "基于流动性扫荡+回收的买卖信号指标。识别摆动高低点的止损猎杀,ATR过滤,HTF趋势对齐。", "default_params": {"piv_len": 8, "atr_len": 14}},
    "volume": {
        "name": "成交量",
        "description": "识别倍率、高低量、平量、梯量、连续缩量，并计算相对量能与连续次数。",
        "default_params": {
            "shrink_max": 0.8,
            "increase_min": 1.2,
            "double_min": 2.0,
            "triple_min": 3.0,
            "multiple_min": 4.0,
            "lookback": 20,
            "flat_tolerance": 0.08,
            "sequence_length": 3,
            "relative_period": 20,
        },
        "outputs": [
            {"field": "ratio", "label": "相邻量比"},
            {"field": "relative_volume", "label": "相对量能"},
            {"field": "volume_class", "label": "倍率分类"},
            {"field": "is_shrink_volume", "label": "达到缩量"},
            {"field": "is_increase_volume", "label": "达到增量"},
            {"field": "is_double_volume", "label": "达到倍量"},
            {"field": "is_triple_volume", "label": "达到三倍量"},
            {"field": "is_multiple_volume", "label": "达到多倍量"},
            {"field": "is_high_volume", "label": "高量柱"},
            {"field": "is_low_volume", "label": "低量柱"},
            {"field": "is_flat_volume", "label": "平量柱"},
            {"field": "is_ladder_volume", "label": "梯量柱"},
            {"field": "is_contracting_volume", "label": "连续缩量"},
            {"field": "increase_streak", "label": "连续放量根数"},
            {"field": "shrink_streak", "label": "连续缩量根数"},
        ],
    },
    "volume_structure": {
        "name": "量柱结构",
        "description": "识别关键量柱、将军柱、黄金柱，并生成关键量柱线和黄金线。确认信号不使用未来数据。",
        "default_params": {"lookback": 20, "key_ratio_min": 1.8, "confirm_bars": 3, "break_tolerance": 0.0},
        "outputs": [
            {"field": "key_pillar", "label": "关键量柱出现"},
            {"field": "key_line", "label": "关键量柱线"},
            {"field": "above_key_line", "label": "站上关键量柱线"},
            {"field": "key_line_distance_pct", "label": "距关键线百分比"},
            {"field": "key_line_break", "label": "跌破关键量柱线"},
            {"field": "general_confirmed", "label": "将军柱确认"},
            {"field": "golden_confirmed", "label": "黄金柱确认"},
            {"field": "golden_line", "label": "黄金线"},
            {"field": "above_golden_line", "label": "站上黄金线"},
            {"field": "golden_line_distance_pct", "label": "距黄金线百分比"},
            {"field": "golden_line_break", "label": "跌破黄金线"},
        ],
    },
    "dilun_structure": {
        "name": "帝论·合理价格",
        "description": "基于确认分型和三段走势折叠，识别合理价格区间、回归、回归失败与态势末端脱离。",
        "default_params": {
            "departure_confirm_bars": 2,
            "true_departure_bars": 3,
            "false_departure_max_bars": 5,
            "retest_window": 10,
            "maturity_bars": 8,
            "maturity_folds": 4,
            "breakout_buffer_pct": 0.0,
        },
        "outputs": [
            {"field": "fractal_confirmed", "label": "确认分型方向"},
            {"field": "top_fractal_confirmed", "label": "顶分型确认"},
            {"field": "bottom_fractal_confirmed", "label": "底分型确认"},
            {"field": "trend_confirmed", "label": "趋势确认方向"},
            {"field": "trend_direction", "label": "当前趋势方向"},
            {"field": "trend_broken", "label": "趋势破坏方向"},
            {"field": "zone_confirmed", "label": "合理价格区间确认"},
            {"field": "zone_low", "label": "合理价格下沿"},
            {"field": "zone_high", "label": "合理价格上沿"},
            {"field": "zone_mid", "label": "合理价格中轴"},
            {"field": "zone_width_pct", "label": "合理区间宽度"},
            {"field": "zone_age", "label": "态势持续根数"},
            {"field": "fold_count", "label": "折叠次数"},
            {"field": "zone_mature", "label": "态势成熟"},
            {"field": "inside_zone", "label": "位于合理区间"},
            {"field": "zone_position", "label": "相对合理区间位置"},
            {"field": "distance_to_zone_pct", "label": "距合理区间百分比"},
            {"field": "departure_direction", "label": "脱离方向"},
            {"field": "departure_bars", "label": "脱离持续根数"},
            {"field": "zone_departure_signal", "label": "脱离确认"},
            {"field": "zone_return_signal", "label": "脱离后回归"},
            {"field": "false_departure_signal", "label": "假脱离回归"},
            {"field": "return_failure_signal", "label": "回归失败转折"},
            {"field": "true_departure_signal", "label": "真脱离确认"},
            {"field": "terminal_breakout_signal", "label": "态势末端脱离"},
        ],
    },
    "chip_distribution": {
        "name": "筹码分布",
        "description": "以近500日日线筹码为基准，支持日线、30分钟和5分钟逐K线演进，估算筹码峰、成本区间和获利盘。",
        "default_params": {
            "bins": 120, "lookback": 500, "min_turnover_days": 20,
            "near_range_pct": 3.0, "support_range_pct": 5.0,
            "peak_prominence": 0.5, "min_peak_distance": 5,
            "trend_period": 5, "migration_threshold_pct": 1.0,
            "concentration_change_threshold": 0.5,
            "pressure_release_threshold": 5.0, "retest_tolerance_pct": 1.0,
        },
        "outputs": [
            {"field": "peak_price", "label": "主筹码峰"},
            {"field": "average_cost", "label": "平均成本"},
            {"field": "profit_ratio", "label": "获利盘比例"},
            {"field": "range70_low", "label": "70%成本下沿"},
            {"field": "range70_high", "label": "70%成本上沿"},
            {"field": "concentration70", "label": "70%集中度"},
            {"field": "range90_low", "label": "90%成本下沿"},
            {"field": "range90_high", "label": "90%成本上沿"},
            {"field": "concentration90", "label": "90%集中度"},
            {"field": "price_vs_peak_pct", "label": "距主峰百分比"},
            {"field": "price_vs_average_pct", "label": "距平均成本百分比"},
            {"field": "above_peak", "label": "站上主筹码峰"},
            {"field": "above_average_cost", "label": "站上平均成本"},
            {"field": "inside_range70", "label": "位于70%成本区间"},
            {"field": "inside_range90", "label": "位于90%成本区间"},
            {"field": "support_chip_ratio", "label": "下方支撑筹码"},
            {"field": "pressure_chip_ratio", "label": "上方压力筹码"},
            {"field": "upper_chip_ratio", "label": "套牢筹码比例"},
            {"field": "near_price_chip_ratio", "label": "现价附近筹码"},
            {"field": "dominant_peak_ratio", "label": "主峰筹码占比"},
            {"field": "peak_count", "label": "有效筹码峰数量"},
            {"field": "single_peak", "label": "单峰密集"},
            {"field": "double_peak", "label": "双峰结构"},
            {"field": "secondary_peak_price", "label": "次筹码峰"},
            {"field": "peak_separation_pct", "label": "主次峰间距"},
            {"field": "peak_change_pct", "label": "主峰迁移幅度"},
            {"field": "average_cost_change_pct", "label": "平均成本变化"},
            {"field": "profit_ratio_change", "label": "获利盘变化"},
            {"field": "concentration70_change", "label": "集中度变化"},
            {"field": "peak_direction", "label": "主峰迁移方向"},
            {"field": "average_cost_direction", "label": "平均成本方向"},
            {"field": "chip_converging", "label": "筹码正在集中"},
            {"field": "chip_spreading", "label": "筹码正在发散"},
            {"field": "cross_peak_up", "label": "上穿主筹码峰"},
            {"field": "cross_peak_down", "label": "下穿主筹码峰"},
            {"field": "cross_average_cost_up", "label": "上穿平均成本"},
            {"field": "cross_average_cost_down", "label": "下穿平均成本"},
            {"field": "break_range70_high", "label": "突破70%成本上沿"},
            {"field": "break_range70_low", "label": "跌破70%成本下沿"},
            {"field": "retest_peak", "label": "回踩主峰"},
            {"field": "single_peak_formed", "label": "单峰密集形成"},
            {"field": "double_peak_formed", "label": "双峰结构形成"},
            {"field": "peak_shifted_up", "label": "主峰确认上移"},
            {"field": "peak_shifted_down", "label": "主峰确认下移"},
            {"field": "concentration_started", "label": "开始集中"},
            {"field": "pressure_released", "label": "上方压力释放"},
            {"field": "support_strengthened", "label": "下方支撑增强"},
            {"field": "coverage_ratio", "label": "数据覆盖率"},
        ],
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
            outputs=meta.get("outputs", []) if not is_public or policy.show_details else [],
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
    ds = get_data_service()
    requires_chip_data = any(ind.type == "chip_distribution" for ind in req.indicators)
    chip_context_error: str | None = None
    chip_klines: list[dict] | None = None
    indicator_context: dict = {}
    try:
        kline_result = await ds.fetch_klines(
            symbol=req.symbol, timeframe=req.timeframe, limit=req.kline_limit,
        )
    except Exception as e:
        logger.error(f"POST /indicator/calculate kline fetch failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    klines = kline_result["data"]
    chip_klines = klines

    if requires_chip_data:
        if (
            req.timeframe not in {"1d", "30m", "5m"}
            or not req.symbol
            or not req.symbol[0].isdigit()
        ):
            chip_context_error = "筹码分布目前仅支持股票的日线、30分钟和5分钟"
        else:
            try:
                if req.timeframe == "1d" and any(
                    bar.get("turnover_rate") is None
                    or bar.get("circulating_shares") is None
                    or bar.get("adjustment_factor") is None
                    for bar in chip_klines
                ):
                    logger.info("chip fields incomplete for %s, refreshing chip data only", req.symbol)
                    chip_result = await ds.fetch_klines(
                        symbol=req.symbol,
                        timeframe=req.timeframe,
                        limit=req.kline_limit,
                        force_refresh=True,
                    )
                    chip_klines = chip_result["data"]
                if req.timeframe != "1d":
                    lookback = max(
                        int(ind.params.get("lookback", 500))
                        for ind in req.indicators
                        if ind.type == "chip_distribution"
                    )
                    daily_limit = min(max(lookback, 500), 1000)
                    daily_result = await ds.fetch_klines(
                        symbol=req.symbol, timeframe="1d", limit=daily_limit,
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
                            limit=daily_limit,
                            force_refresh=True,
                        )
                    indicator_context["daily_klines"] = daily_result["data"]
            except Exception as error:
                chip_context_error = f"筹码分布附加数据加载失败：{error}"
                logger.warning("chip context unavailable for %s/%s: %s", req.symbol, req.timeframe, error)

    svc = get_indicator_service()
    results: list[IndicatorResultItem] = []
    errors: list[IndicatorErrorItem] = []

    for ind in req.indicators:
        policy = policies.get(ind.type)
        if public_surface and (not policy or not policy.public_visible):
            errors.append(IndicatorErrorItem(
                type=ind.type, code="not_available", message="该指标在当前工作区不可用",
            ))
            continue
        if ind.type == "chip_distribution" and chip_context_error:
            errors.append(IndicatorErrorItem(
                type=ind.type, code="context_unavailable", message=chip_context_error,
            ))
            continue
        try:
            source_klines = chip_klines if ind.type == "chip_distribution" else klines
            # 每个计算器获得独立的输入副本，防止第三方或未来指标原地修改共享K线。
            calculation_klines = [dict(bar) for bar in source_klines]
            calculation_context = None
            if ind.type == "chip_distribution":
                calculation_context = {
                    "daily_klines": [dict(bar) for bar in indicator_context.get("daily_klines", [])]
                } if indicator_context.get("daily_klines") else {}
            result = await svc.calculate(
                symbol=req.symbol,
                timeframe=req.timeframe,
                indicator_type=ind.type,
                params=ind.params,
                klines=calculation_klines,
                context=calculation_context,
            )
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
            errors.append(IndicatorErrorItem(
                type=ind.type, code="invalid_parameters", message=str(e),
            ))
        except Exception as e:
            logger.error(f"POST /indicator/calculate {ind.type} failed: {e}", exc_info=True)
            errors.append(IndicatorErrorItem(
                type=ind.type, code="calculation_failed", message=str(e),
            ))

    logger.info(
        "POST /indicator/calculate -> %s indicators computed, %s isolated failures",
        len(results), len(errors),
    )
    return IndicatorCalculateResponse(
        symbol=req.symbol,
        timeframe=req.timeframe,
        results=results,
        errors=errors,
    )
