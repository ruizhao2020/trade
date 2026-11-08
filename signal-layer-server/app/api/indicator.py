import logging
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from sqlalchemy import select
from app.api.security import optional_user, require_permission
from app.api.deps import get_data_service, get_indicator_service
from app.db import get_session
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.effectiveness import IndicatorEffectiveness
from app.services.public_site_service import ensure_public_indicator, public_indicator_feature_map, public_indicator_map
from app.services.auth_service import permission_codes
from app.schemas.indicator import (
    IndicatorCalculateRequest, IndicatorCalculateResponse,
    IndicatorResultItem, IndicatorErrorItem, IndicatorInfo, IndicatorListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/indicator", tags=["indicator"])

# 结论优先序：同一个字段有多个方向/规则时取证据最强的一条
_VERDICT_RANK = {
    "valid": 0, "filter_only": 1, "weak": 2, "rejected": 3,
    "insufficient": 4, "unverified": 5,
}


async def _effectiveness_verdicts(
    session: AsyncSession, timeframe: str, universe: str,
) -> dict[tuple[str, str], str]:
    """(指标类型, 字段) → 结论。只给私域用：它决定哪些字段能进策略。"""
    rows = (await session.execute(select(
        IndicatorEffectiveness.indicator_type,
        IndicatorEffectiveness.field,
        IndicatorEffectiveness.verdict,
    ).where(
        IndicatorEffectiveness.timeframe == timeframe,
        IndicatorEffectiveness.universe == universe,
    ))).all()
    best: dict[tuple[str, str], str] = {}
    for ind_type, field_name, verdict in rows:
        key = (ind_type, field_name)
        if key not in best or _VERDICT_RANK.get(verdict, 9) < _VERDICT_RANK.get(best[key], 9):
            best[key] = verdict
    return best


# 指标元信息(前端指标库展示用)
INDICATOR_META: dict[str, dict] = {
    "position": {
        "name": "位置",
        "description": (
            "价格在近期区间中的相对位置、距高点回撤、与缠论中枢的关系。"
            "给形态加「顶部/中部/底部」的前置条件：位置分位 0=区间最低、100=区间最高；"
            "中枢位置 1=中枢上方、0=中枢内、-1=中枢下方。"
        ),
        "default_params": {"window": 120},
        "outputs": [
            {"field": "position_pct", "label": "位置分位(0-100)", "description": "收盘价在最近窗口区间里的分位：0 是区间最低、100 是区间最高。用来区分顶部/中部/底部。"},
            {"field": "drawdown_pct", "label": "距高点回撤%", "description": "收盘价距位置窗口最高价的回撤百分比。"},
            {"field": "zone_position", "label": "中枢位置(上/中/下)", "description": "收盘价相对最近一个笔中枢的位置：1=中枢上方、0=中枢内、-1=中枢下方。"},
        ],
    },
    "ma": {
        "name": "移动平均线",
        "description": "趋势跟踪指标，支持向上、向下、方向反转、支撑和压制判断。",
        "default_params": {"period": 5, "touch_tolerance_pct": 0.5},
        # 显式声明输出：不声明的话编辑器会回退到 plots 且拿不到有效性结论，
        # 均线条件会全部落进「未验证」。
        "outputs": [
            {"field": "value", "label": "均线值", "description": "该周期的均线值（收盘价的简单移动平均）。"},
        ],
    },
    "macd": {
        "name": "MACD",
        "description": (
            "指数平滑异同移动平均线。用相邻红/绿柱群的面积对比标注顶背驰与底背驰："
            "后一群的柱体面积更小，价格却创了新高/新低，说明推动力在衰减。"
            "箭头连接前一群与后一群的峰位。"
        ),
        "default_params": {"fast": 12, "slow": 26, "signal": 9, "divergence_min_bars": 3},
        # 显式声明输出：不声明的话条件编辑器会回退到 plots，
        # 顶/底背驰这两个事件字段就选不到，策略里也没法做筛选。
        "outputs": [
            {"field": "dif", "label": "DIF", "description": "快慢 EMA 之差，代表短期动能。"},
            {"field": "dea", "label": "DEA", "description": "DIF 的 EMA，作为信号线。"},
            {"field": "histogram", "label": "MACD 柱", "description": "DIF 与 DEA 之差（柱体）：正值红柱、负值绿柱。"},
            {"field": "top_divergence", "kind": "event", "label": "顶背驰", "direction": "short", "description": "相邻两个红柱群里后一群更小，价格却创新高。上涨动能衰减。"},
            {"field": "bottom_divergence", "kind": "event", "label": "底背驰", "direction": "long", "description": "相邻两个绿柱群里后一群更小，价格却创新低。下跌动能衰减。"},
        ],
    },
    "bollinger": {
        "name": "布林带",
        "description": "Bollinger Bands 通道指标。带宽＝上轨−下轨，与若干根之前比较、幅度超过阈值即判定开口（走阔）或收口（收窄）。",
        "default_params": {
            "period": 20, "std": 2.0,
            "squeeze_lookback": 10, "squeeze_threshold_pct": 30.0,
        },
        # 显式声明：不声明的话条件编辑器会回退到 render.plots 的字段（UP/MID/LOW
        # 这类英文图例名），而且带宽字段就选不到——开口/收口也就无从表达。
        "outputs": [
            {"field": "upper", "label": "上轨", "description": "布林带上轨 = 中轨 + 标准差倍数 × 标准差。"},
            {"field": "middle", "label": "中轨", "description": "布林带中轨，即周期均线。"},
            {"field": "lower", "label": "下轨", "description": "布林带下轨 = 中轨 − 标准差倍数 × 标准差。"},
            {"field": "bandwidth", "label": "带宽", "description": "上轨与下轨的差值，衡量波动幅度。"},
            {"field": "bandwidth_pct", "label": "带宽%（相对中轨）", "description": "带宽相对中轨的百分比，便于跨标的比较。"},
            # 开口/收口是形态类事件：与若干根之前的带宽比较、超过阈值才算，
            # 因此按事件型字段处理（条件编辑器不给它挂 >= 这样的比较）
            {"field": "band_squeeze", "label": "收口", "kind": "event", "direction": "none", "description": "带宽相对若干根之前明显收窄。波动收敛，常见于变盘前。"},
            {"field": "band_expand", "label": "开口", "kind": "event", "direction": "none", "description": "带宽明显走阔。波动放大，趋势启动或加速。"},
        ],
    },
    "liquidity_sweep": {
        "name": "流动性扫荡反转",
        "description": (
            "基于流动性扫荡+回收的买卖信号指标。识别摆动高低点的止损猎杀，用 ATR 过滤刺穿深度，"
            "信号标记挂在被扫的那个价位上（SSL/BSL SWEEP）。"
            "不含 SL/TP 交易模型与 R 倍数统计——参考脚本的这部分属于交易模型层，本指标只给信号。"
        ),
        "default_params": {"piv_len": 8, "atr_len": 14},
        # 显式声明：不声明的话条件编辑器会回退到 render.plots，而信号现在走 markers，
        # 回退源为空 → 界面上一个可选字段都没有。
        "outputs": [
            {"field": "bull_signal", "kind": "event", "label": "看涨扫荡信号", "direction": "long", "description": "向下扫掉前低后收回。止损猎杀后的看涨反转。"},
            {"field": "bear_signal", "kind": "event", "label": "看跌扫荡信号", "direction": "short", "description": "向上扫掉前高后回落。诱导突破后的看跌反转。"},
            {"field": "bull_level", "label": "被扫的支撑水平", "description": "看涨扫荡信号所扫掉的支撑价位。"},
            {"field": "bear_level", "label": "被扫的压力水平", "description": "看跌扫荡信号所扫掉的压力价位。"},
            {"field": "atr", "label": "ATR（波动率尺度）", "description": "ATR 波动率尺度，用于过滤刺穿深度。"},
        ],
    },
    "liquidity_zone": {
        "name": "流动性聚集区",
        "description": "用等高等低（同向摆动枢轴落在 ATR 缩放的容差内）识别流动性聚集区，并跟踪它生成→聚集→被扫荡→消失的过程。图上按时间段画方框：聚集阶段实线，被扫荡后转虚线并按被拿走的比例填充。",
        "default_params": {
            "span": 5,
            "atr_len": 14,
            "eq_atr": 0.35,
            "min_touches": 2,
            "zone_width_atr": 0.5,
            "pierce_atr": 0.15,
            "reclaim_bars": 3,
            "break_bars": 2,
            "max_age_bars": 250,
            "max_zones": 4,
        },
        # 只列因果的决策字段，且只描述"仍在聚集阶段"的区。
        # zone_{k}_low/high/consumed/from_top 供前端画方框，依赖"最后一根时该区
        # 是否还成立"，不是因果序列，因此不进白名单。
        "outputs": [
            {"field": "zone_count", "label": "聚集中的区数量", "description": "当前仍处在聚集阶段的流动性区数量。"},
            {"field": "nearest_zone_low", "label": "最近聚集区下沿", "description": "离现价最近的聚集区下沿。"},
            {"field": "nearest_zone_high", "label": "最近聚集区上沿", "description": "离现价最近的聚集区上沿。"},
            {"field": "nearest_zone_touches", "label": "最近聚集区触碰次数", "description": "最近聚集区被触碰的次数，次数越多聚集越强。"},
            {"field": "nearest_zone_consumed_pct", "label": "最近聚集区已被拿走比例", "description": "最近聚集区已被扫掉的筹码比例。"},
            {"field": "nearest_zone_swept", "kind": "event", "label": "最近聚集区已被扫荡", "description": "最近聚集区是否已经被扫荡。"},
            {"field": "price_in_zone", "kind": "event", "label": "价格位于聚集区内", "description": "现价是否位于聚集区内部。"},
            {"field": "distance_to_zone_pct", "label": "距聚集区百分比", "description": "现价距合理区间的百分比。"},
            {"field": "sweep_up", "kind": "event", "label": "上沿被扫荡", "description": "价格向上扫过聚集区上沿，流动性被拿走。"},
            {"field": "sweep_down", "kind": "event", "label": "下沿被扫荡", "description": "价格向下扫过聚集区下沿，流动性被拿走。"},
            {"field": "zone_broken", "kind": "event", "label": "聚集区被破位", "description": "最近聚集区是否已被有效突破。"},
        ],
    },
    "support_resistance": {
        "name": "压力位支撑位",
        "description": "用摆动高低点聚类出压力位与支撑位：容差按 ATR 缩放，按触碰次数与时间衰减排重要性。图上把仍有效的位画成水平线段，破位后角色互换（压力变支撑）。",
        "default_params": {
            "span": 5,
            "atr_len": 14,
            "tolerance_atr": 0.5,
            "min_touches": 2,
            "touch_separation": 3,
            "max_levels": 6,
            "max_age_bars": 250,
            "recency_half_life": 120,
        },
        # 只列因果的决策字段。level_1..N 是渲染用途（把当前有效位回填到首次触碰处），
        # 不在白名单里因此在条件编辑器中不可选——它依赖未来是否被破，不是因果序列。
        "outputs": [
            {"field": "nearest_support", "label": "最近支撑位", "description": "现价下方最近的支撑位价格。"},
            {"field": "nearest_resistance", "label": "最近压力位", "description": "现价上方最近的压力位价格。"},
            {"field": "nearest_support_touches", "label": "支撑位触碰次数", "description": "最近支撑位被触碰的次数。"},
            {"field": "nearest_resistance_touches", "label": "压力位触碰次数", "description": "最近压力位被触碰的次数。"},
            {"field": "distance_to_support_pct", "label": "距支撑位百分比", "description": "现价距最近支撑位的百分比。"},
            {"field": "distance_to_resistance_pct", "label": "距压力位百分比", "description": "现价距最近压力位的百分比。"},
            {"field": "at_support", "kind": "event", "label": "正在测试支撑位", "description": "现价是否正在触及支撑位。"},
            {"field": "at_resistance", "kind": "event", "label": "正在测试压力位", "description": "现价是否正在触及压力位。"},
            {"field": "support_broken", "kind": "event", "label": "支撑位跌破", "description": "支撑位是否已被跌破。"},
            {"field": "resistance_broken", "kind": "event", "label": "压力位突破", "description": "压力位是否已被突破。"},
            {"field": "level_count", "label": "有效位数量", "description": "当前识别到的支撑/压力位数量。"},
        ],
    },
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
            {"field": "ratio", "label": "相邻量比", "description": "当根成交量与前一根的比值。"},
            {"field": "relative_volume", "label": "相对量能", "description": "当根成交量相对前若干根基线中位数的倍数。"},
            {"field": "volume_class", "label": "倍率分类", "description": "量能分类编码：缩量/平量/增量/倍量/三倍量/多倍量。"},
            {"field": "is_shrink_volume", "kind": "event", "label": "达到缩量", "description": "当根是否达到缩量标准。"},
            {"field": "is_increase_volume", "kind": "event", "label": "达到增量", "description": "当根是否达到增量标准。"},
            {"field": "is_double_volume", "kind": "event", "label": "达到倍量", "description": "当根是否达到倍量标准。"},
            {"field": "is_triple_volume", "kind": "event", "label": "达到三倍量", "description": "当根是否达到三倍量标准。"},
            {"field": "is_multiple_volume", "kind": "event", "label": "达到多倍量", "description": "当根是否达到多倍量标准。"},
            {"field": "is_high_volume", "kind": "event", "label": "高量柱", "description": "当根是否属于高量柱。"},
            {"field": "is_low_volume", "kind": "event", "label": "低量柱", "description": "当根是否属于低量柱。"},
            {"field": "is_flat_volume", "kind": "event", "label": "平量柱", "description": "当根是否与前一周期量能持平。"},
            {"field": "is_ladder_volume", "kind": "event", "label": "梯量柱", "description": "当根是否形成梯量（连续放量）。"},
            {"field": "is_contracting_volume", "kind": "event", "label": "连续缩量", "description": "当根是否处在连续缩量序列中。"},
            {"field": "increase_streak", "label": "连续放量根数", "description": "连续放量的根数。"},
            {"field": "shrink_streak", "label": "连续缩量根数", "description": "连续缩量的根数。"},
        ],
    },
    "volume_structure": {
        "name": "量柱结构",
        "description": "识别关键量柱、将军柱、黄金柱，并生成关键量柱线和黄金线。确认信号不使用未来数据。",
        "default_params": {"lookback": 20, "key_ratio_min": 1.8, "confirm_bars": 3, "break_tolerance": 0.0},
        "outputs": [
            {"field": "key_pillar", "kind": "event", "label": "关键量柱出现", "direction": "none", "description": "出现远超基线的关键量柱，是后续关键量柱线的起点。"},
            {"field": "key_line", "label": "关键量柱线", "description": "关键量柱确立的水平线，常作为回踩支撑/破位参考。"},
            {"field": "above_key_line", "kind": "event", "label": "站上关键量柱线", "direction": "long", "description": "收盘站上关键量柱线，视为走强。"},
            {"field": "key_line_distance_pct", "label": "距关键线百分比", "description": "现价距关键量柱线的百分比。"},
            {"field": "key_line_break", "kind": "event", "label": "跌破关键量柱线", "direction": "short", "description": "收盘跌破关键量柱线，视为走弱。"},
            {"field": "general_confirmed", "kind": "event", "label": "将军柱确认", "direction": "long", "description": "将军柱确认：关键量柱之后按确认根数站稳，属于较强的量柱结构。"},
            {"field": "golden_confirmed", "kind": "event", "label": "黄金柱确认", "direction": "long", "description": "黄金柱确认：比将军柱更强的量柱结构。"},
            {"field": "golden_line", "label": "黄金线", "description": "黄金柱确立的水平线。"},
            {"field": "above_golden_line", "kind": "event", "label": "站上黄金线", "direction": "long", "description": "收盘站上黄金线，强势延续。"},
            {"field": "golden_line_distance_pct", "label": "距黄金线百分比", "description": "现价距黄金线的百分比。"},
            {"field": "golden_line_break", "kind": "event", "label": "跌破黄金线", "direction": "short", "description": "收盘跌破黄金线，强势被破坏。"},
        ],
    },
    "volume_price": {
        "name": "量价",
        "description": (
            "量能与价格的结合形态：放量突破、缩量回调、量价齐升、放量滞涨、"
            "天量天价、地量地价、底部放量、放量冲高回落。量能是否放大按当根之前的基线中位数衡量；"
            "缩量回调、量价齐升、地量地价按连续多根 K 线判定。"
        ),
        "default_params": {
            "breakout_window": 20,
            "baseline_window": 20,
            "position_window": 60,
            "consecutive_bars": 3,
            "volume_ratio_min": 1.5,
            "shrink_max": 0.7,
            "stagnant_pct": 1.0,
            "stagnant_max_drawdown_pct": 10.0,
            "low_position_pct": 20.0,
        },
        "outputs": [
            # direction 是评测角色：long=入场、short=出场/风险、none=由评测决定方向。
            {"field": "volume_breakout", "kind": "event", "label": "放量突破", "direction": "long", "description": "收盘价突破近 breakout_window 根的最高价，且相对量能达到放量阈值。突破有量配合，有效性较高。"},
            {"field": "shrink_pullback", "kind": "event", "label": "缩量回调", "direction": "long", "description": "连续多根收盘走低、量能低于缩量上限，且没有跌破前低。抛压不大，属于良性回调。"},
            {"field": "price_volume_rise", "kind": "event", "label": "量价齐升", "direction": "long", "description": "连续多根收盘走高、成交量逐根放大。价涨量增，上涨结构健康。"},
            {"field": "volume_stagnation", "kind": "event", "label": "放量滞涨", "direction": "short", "description": "放量但涨幅只有 0~1%，且价格处在近期高位。高位放量却涨不动，是顶部预警。"},
            {"field": "climax_top", "kind": "event", "label": "天量天价", "direction": "short", "description": "成交量达到位置窗口最大值，收盘也在窗口最高附近。天量天价，情绪高潮、分歧最大。"},
            {"field": "exhaustion_bottom", "kind": "event", "label": "地量地价", "direction": "long", "description": "连续多根缩量，且价格处在近期低位。地量地价，抛压衰竭。"},
            {"field": "bottom_volume", "kind": "event", "label": "底部放量", "direction": "long", "description": "低位出现放量阳线。恐慌之后有资金承接。"},
            {"field": "failed_breakout", "kind": "event", "label": "放量冲高回落", "direction": "short", "description": "盘中越过前高但收盘收回前高之下，同时放量。上冲被压回，属于假突破。"},
            {"field": "relative_volume", "label": "相对量能", "description": "当根成交量相对前若干根基线中位数的倍数。"},
            {"field": "breakout_pct", "label": "距前高百分比", "description": "收盘价超出前高的百分比。"},
            {"field": "drawdown_pct", "label": "距区间高点回撤", "description": "收盘价距位置窗口最高价的回撤百分比。"},
            {"field": "change_pct", "label": "当日涨幅", "description": "当根涨跌幅（%）。"},
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
            {"field": "fractal_confirmed", "kind": "event", "label": "确认分型方向", "description": "分型是否已确认（需要后续 K 线验证）。"},
            {"field": "top_fractal_confirmed", "kind": "event", "label": "顶分型确认", "description": "是否确认了顶分型。"},
            {"field": "bottom_fractal_confirmed", "kind": "event", "label": "底分型确认", "description": "是否确认了底分型。"},
            {"field": "trend_confirmed", "kind": "event", "label": "趋势确认方向", "description": "趋势方向是否已确认。"},
            {"field": "trend_direction", "kind": "event", "label": "当前趋势方向", "description": "当前趋势方向：1=向上、-1=向下、0=未定。"},
            {"field": "trend_broken", "kind": "event", "label": "趋势破坏方向", "description": "趋势是否已被破坏。"},
            {"field": "zone_confirmed", "kind": "event", "label": "合理价格区间确认", "description": "合理价格区间是否已确认成立。"},
            {"field": "zone_low", "label": "合理价格下沿", "description": "合理价格区间下沿。"},
            {"field": "zone_high", "label": "合理价格上沿", "description": "合理价格区间上沿。"},
            {"field": "zone_mid", "label": "合理价格中轴", "description": "合理价格区间中轴。"},
            {"field": "zone_width_pct", "label": "合理区间宽度", "description": "合理区间的宽度（相对中轴）。"},
            {"field": "zone_age", "label": "态势持续根数", "description": "当前合理区间已经持续的根数。"},
            {"field": "fold_count", "label": "折叠次数", "description": "区间内发生的折叠次数，越多说明震荡越充分。"},
            {"field": "zone_mature", "kind": "event", "label": "态势成熟", "description": "合理价格区间是否已经成熟（持续足够根数/折叠）。"},
            {"field": "inside_zone", "kind": "event", "label": "位于合理区间", "description": "现价是否位于合理价格区间内部。"},
            {"field": "zone_position", "kind": "event", "label": "相对合理区间位置", "description": "现价相对合理区间的位置：上/中/下。"},
            {"field": "distance_to_zone_pct", "label": "距合理区间百分比", "description": "现价距合理区间的百分比。"},
            {"field": "departure_direction", "kind": "event", "label": "脱离方向", "description": "脱离合理区间的方向：1=向上、-1=向下。"},
            {"field": "departure_bars", "label": "脱离持续根数", "description": "价格脱离合理区间后持续的根数。"},
            {"field": "zone_departure_signal", "kind": "event", "label": "脱离确认", "description": "价格脱离合理区间的信号。"},
            {"field": "zone_return_signal", "kind": "event", "label": "脱离后回归", "description": "价格重新回到合理区间的信号。"},
            {"field": "false_departure_signal", "kind": "event", "label": "假脱离回归", "description": "假脱离：离开后又快速回到区间。"},
            {"field": "return_failure_signal", "kind": "event", "label": "回归失败转折", "description": "回归失败：回到区间边缘后再次离开。"},
            {"field": "true_departure_signal", "kind": "event", "label": "真脱离确认", "description": "真脱离：离开后不再回到区间。"},
            {"field": "terminal_breakout_signal", "kind": "event", "label": "态势末端脱离", "description": "区间末端的突破信号。"},
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
            {"field": "peak_price", "label": "主筹码峰", "description": "筹码分布中最密集的价位（主峰）。"},
            {"field": "average_cost", "label": "平均成本", "description": "全部持仓筹码的平均成本。"},
            {"field": "profit_ratio", "label": "获利盘比例", "description": "现价之上获利筹码占全部筹码的比例。"},
            {"field": "range70_low", "label": "70%成本下沿", "description": "覆盖 70% 筹码的成本区间下沿。"},
            {"field": "range70_high", "label": "70%成本上沿", "description": "覆盖 70% 筹码的成本区间上沿。"},
            {"field": "concentration70", "label": "70%集中度", "description": "70% 成本区间的集中度，越高说明筹码越集中。"},
            {"field": "range90_low", "label": "90%成本下沿", "description": "覆盖 90% 筹码的成本区间下沿。"},
            {"field": "range90_high", "label": "90%成本上沿", "description": "覆盖 90% 筹码的成本区间上沿。"},
            {"field": "concentration90", "label": "90%集中度", "description": "90% 成本区间的集中度。"},
            {"field": "price_vs_peak_pct", "label": "距主峰百分比", "description": "现价距主筹码峰的百分比。"},
            {"field": "price_vs_average_pct", "label": "距平均成本百分比", "description": "现价距平均成本的百分比。"},
            {"field": "above_peak", "kind": "event", "label": "站上主筹码峰", "description": "现价是否在主力筹码峰之上。"},
            {"field": "above_average_cost", "kind": "event", "label": "站上平均成本", "description": "现价是否高于平均成本。"},
            {"field": "inside_range70", "kind": "event", "label": "位于70%成本区间", "description": "现价是否处于 70% 成本区间内部。"},
            {"field": "inside_range90", "kind": "event", "label": "位于90%成本区间", "description": "现价是否处于 90% 成本区间内部。"},
            {"field": "support_chip_ratio", "label": "下方支撑筹码", "description": "位于现价下方的筹码占比（潜在支撑）。"},
            {"field": "pressure_chip_ratio", "label": "上方压力筹码", "description": "位于现价上方的筹码占比（潜在压力）。"},
            {"field": "upper_chip_ratio", "label": "套牢筹码比例", "description": "套牢筹码占全部筹码的比例。"},
            {"field": "near_price_chip_ratio", "label": "现价附近筹码", "description": "集中在现价附近的筹码占比。"},
            {"field": "dominant_peak_ratio", "label": "主峰筹码占比", "description": "主峰筹码占全部筹码的比例。"},
            {"field": "peak_count", "label": "有效筹码峰数量", "description": "有效筹码峰的数量，两个峰即双峰结构。"},
            {"field": "single_peak", "kind": "event", "label": "单峰密集", "description": "筹码是否呈单峰结构。"},
            {"field": "double_peak", "kind": "event", "label": "双峰结构", "description": "筹码是否呈双峰结构。"},
            {"field": "secondary_peak_price", "label": "次筹码峰", "description": "除主峰外最明显的次筹码峰价位。"},
            {"field": "peak_separation_pct", "label": "主次峰间距", "description": "主峰与次峰之间的价格间距。"},
            {"field": "peak_change_pct", "label": "主峰迁移幅度", "description": "主筹码峰相对前一根的迁移幅度。"},
            {"field": "average_cost_change_pct", "label": "平均成本变化", "description": "平均成本相对前一根的变化幅度。"},
            {"field": "profit_ratio_change", "label": "获利盘变化", "description": "获利盘比例相对前一根的变化。"},
            {"field": "concentration70_change", "label": "集中度变化", "description": "70% 集中度相对前一根的变化。"},
            {"field": "peak_direction", "kind": "event", "label": "主峰迁移方向", "description": "主筹码峰的迁移方向：1=上移、-1=下移。"},
            {"field": "average_cost_direction", "kind": "event", "label": "平均成本方向", "description": "平均成本的迁移方向。"},
            {"field": "chip_converging", "kind": "event", "label": "筹码正在集中", "description": "筹码是否在收敛（集中度上升）。"},
            {"field": "chip_spreading", "kind": "event", "label": "筹码正在发散", "description": "筹码是否在发散（集中度下降）。"},
            {"field": "cross_peak_up", "kind": "event", "label": "上穿主筹码峰", "description": "现价是否上穿主筹码峰。"},
            {"field": "cross_peak_down", "kind": "event", "label": "下穿主筹码峰", "description": "现价是否下穿主筹码峰。"},
            {"field": "cross_average_cost_up", "kind": "event", "label": "上穿平均成本", "description": "现价是否上穿平均成本。"},
            {"field": "cross_average_cost_down", "kind": "event", "label": "下穿平均成本", "description": "现价是否下穿平均成本。"},
            {"field": "break_range70_high", "kind": "event", "label": "突破70%成本上沿", "description": "现价是否突破 70% 成本区间上沿。"},
            {"field": "break_range70_low", "kind": "event", "label": "跌破70%成本下沿", "description": "现价是否跌破 70% 成本区间下沿。"},
            {"field": "retest_peak", "kind": "event", "label": "回踩主峰", "description": "价格回踩主筹码峰后确认。"},
            {"field": "single_peak_formed", "kind": "event", "label": "单峰密集形成", "description": "单峰结构形成：筹码集中在一个价位附近。"},
            {"field": "double_peak_formed", "kind": "event", "label": "双峰结构形成", "description": "筹码分布出现两个明显密集峰：上方峰是压力，下方峰是支撑，中间相对稀疏。"},
            {"field": "peak_shifted_up", "kind": "event", "label": "主峰确认上移", "description": "主筹码峰明显上移。"},
            {"field": "peak_shifted_down", "kind": "event", "label": "主峰确认下移", "description": "主筹码峰明显下移。"},
            {"field": "concentration_started", "kind": "event", "label": "开始集中", "description": "筹码开始集中。"},
            {"field": "pressure_released", "kind": "event", "label": "上方压力释放", "description": "上方压力筹码被消化。"},
            {"field": "support_strengthened", "kind": "event", "label": "下方支撑增强", "description": "下方支撑筹码增强。"},
            {"field": "coverage_ratio", "label": "数据覆盖率", "description": "筹码估算所用有效换手数据的覆盖率。"},
        ],
    },
}


@router.get("/list", response_model=IndicatorListResponse)
async def list_indicators(
    request: Request,
    user = Depends(optional_user),
    session: AsyncSession = Depends(get_session),
    timeframe: str = Query("1d"),
    universe: str = Query("stock"),
):
    """返回所有可用指标的元信息(前端用于展示指标库)"""
    svc = get_indicator_service()
    available = svc.available_indicators
    private_access = user is not None and "private.access" in permission_codes(user)
    is_public = not private_access or request.headers.get("x-signal-surface", "").lower() == "public"
    policies = await public_indicator_map(session)
    # 字段级有效性结论：前端据此决定哪些字段能进策略（私域才带）
    verdicts = {} if is_public else await _effectiveness_verdicts(session, timeframe, universe)
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
            outputs=[
                {
                    **output,
                    **({} if is_public else {
                        "verdict": verdicts.get((ind_type, output.get("field")), "unverified"),
                    }),
                }
                for output in (meta.get("outputs", []) if not is_public or policy.show_details else [])
            ],
        ))
    await session.commit()
    return IndicatorListResponse(indicators=indicators)


@router.get("/effectiveness")
async def list_effectiveness(
    request: Request,
    user = Depends(optional_user),
    session: AsyncSession = Depends(get_session),
    timeframe: str = Query("1d"),
    universe: str = Query("stock"),
):
    """指标字段有效性结论（仅私域）：策略构建时据此过滤可选字段。"""
    private_access = user is not None and "private.access" in permission_codes(user)
    if not private_access or request.headers.get("x-signal-surface", "").lower() == "public":
        raise HTTPException(status_code=403, detail="有效性结论仅私域可用")
    rows = (await session.execute(select(IndicatorEffectiveness).where(
        IndicatorEffectiveness.timeframe == timeframe,
        IndicatorEffectiveness.universe == universe,
    ).order_by(
        IndicatorEffectiveness.indicator_type,
        IndicatorEffectiveness.field,
    ))).scalars().all()
    return {
        "timeframe": timeframe,
        "universe": universe,
        "items": [
            {
                "indicator_type": row.indicator_type,
                "field": row.field,
                "direction": row.direction,
                "params": row.params,
                "horizon": row.horizon,
                "verdict": row.verdict,
                "sample_n": row.sample_n,
                "hit_rate": row.hit_rate,
                "avg_return": row.avg_return,
                "baseline_return": row.baseline_return,
                "excess_return": row.excess_return,
                "p_value": row.p_value,
                "decay": row.decay,
                "stability": row.stability,
                "scope": row.scope,
                "engine_version": row.engine_version,
                "evaluated_at": row.evaluated_at.isoformat() if row.evaluated_at else None,
            }
            for row in rows
        ],
    }


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
                public_render = result.render.model_copy(update={
                    "plots": public_plots,
                    "markers": public_markers,
                    # 背驰箭头属于信号类展示，公共端默认不透出（即使公开策略打开了标记）。
                    # 确需公开时再加 feature policy 键。
                    "arrows": [],
                })
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
