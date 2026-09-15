"""
============================================================================
条件评估引擎服务
============================================================================

## 功能
评估用户定义的条件模板，判断是否满足交易信号触发条件。
支持多种条件值来源和比较操作符。

## 条件值来源 (resolve)
- price: K 线字段（open/high/low/close/volume），取最新一根的值
- indicator: 指标计算结果（MA/MACD/RSI/筹码分布等），通过 IndicatorService 获取
- chan: 缠论元素数量（买卖点存在性、笔数量、中枢数量等）
- constant: 固定数值
- timeframe: 切换到指定周期后递归解析 inner 值

## 操作符 (compare)
- gt (>): 左值大于右值
- gte (>=): 左值大于等于右值
- lt (<): 左值小于右值
- lte (<=): 左值小于等于右值
- eq (=): 差值绝对值 < 1e-8
- crossAbove: 上穿（当前简化实现为左值 > 右值）
- crossBelow: 下穿（当前简化实现为左值 < 右值）
- rising: 向上（当前值大于上一根值）
- falling: 向下（当前值小于上一根值）
- turnDown: 上转下（上一段向上，本段向下）
- turnUp: 下转上（上一段向下，本段向上）
- between: 区间（左值在右值和 right2 之间）

## 模板逻辑
- AND: 所有条件组都满足才触发 READY（组内各条件也需全部满足）
- OR: 任意条件组满足即触发 READY
- 部分满足状态 (partial): 有部分条件满足但非全部
- 未满足状态 (evaluating): 所有条件都不满足

## 对应前端请求
POST /api/v1/signal/evaluate → ConditionService.evaluate()
"""

from __future__ import annotations
import logging

from app.schemas.signal import (
    ConditionTemplateSchema, ConditionEval, GroupEval, SignalResult,
)
from app.services.indicator_service import IndicatorService
from app.engine.chan import ChanResult

logger = logging.getLogger(__name__)


class ConditionService:
    """条件评估引擎服务。接收模板和数据，返回信号状态"""

    def __init__(self, indicator_service: IndicatorService | None = None):
        self._indicator_service = indicator_service

    async def evaluate(
        self,
        template: ConditionTemplateSchema,
        kline_data: dict[str, list[dict]],
        chan_data: dict[str, ChanResult],
        indicator_data: dict[str, dict[str, list[dict]]],
    ) -> SignalResult:
        primary_tf = template.primary_tf or "1d"
        group_results: list[GroupEval] = []
        total_conds = 0
        satisfied_conds = 0

        logger.info(f"Evaluating template {template.id} with {len(template.condition_groups)} groups, "
                    f"logic={template.logic}")

        for group in template.condition_groups:
            evaluations: list[ConditionEval] = []
            for cond in group.conditions:
                if not cond.enabled:
                    continue
                total_conds += 1

                # 解析左值和右值（支持跨周期、chan、indicator 等多种来源）
                left_val = self._resolve(cond.left, cond, kline_data, chan_data, indicator_data, default_tf=primary_tf)
                right_val = self._resolve(cond.right, cond, kline_data, chan_data, indicator_data, default_tf=primary_tf)
                right2_val = self._resolve(cond.right2, cond, kline_data, chan_data, indicator_data, default_tf=primary_tf) if cond.right2 else None

                prev_left = self._resolve(cond.left, cond, kline_data, chan_data, indicator_data, offset=-1, default_tf=primary_tf)
                prev_right = self._resolve(cond.right, cond, kline_data, chan_data, indicator_data, offset=-1, default_tf=primary_tf)
                prev_prev_left = self._resolve(cond.left, cond, kline_data, chan_data, indicator_data, offset=-2, default_tf=primary_tf)

                satisfied = self._compare(
                    left_val, cond.operator, right_val, prev_left, prev_right, right2_val,
                    prev_prev_left=prev_prev_left,
                )
                diff = 0.0
                if right_val != 0 and isinstance(right_val, (int, float)):
                    diff = abs(left_val - right_val) / abs(right_val) * 100

                evaluations.append(ConditionEval(
                    condition_id=cond.id,
                    satisfied=satisfied,
                    left_value=float(left_val),
                    right_value=float(right_val),
                    diff_percent=round(diff, 2),
                ))
                if satisfied:
                    satisfied_conds += 1

            # 组内 AND 逻辑：所有条件满足才算组满足
            group_satisfied = all(e.satisfied for e in evaluations) if evaluations else False
            group_results.append(GroupEval(
                group_id=group.id,
                evaluations=evaluations,
                satisfied=group_satisfied,
            ))

        # 按模板逻辑汇总
        if template.logic == "AND":
            all_ready = all(g.satisfied for g in group_results) if group_results else False
        else:  # OR
            all_ready = any(g.satisfied for g in group_results) if group_results else False

        if all_ready:
            state = "ready"
        elif satisfied_conds > 0:
            state = "partial"
        else:
            state = "evaluating"

        progress = round(satisfied_conds / total_conds * 100) if total_conds > 0 else 0

        logger.info(f"Template {template.id} evaluated: {satisfied_conds}/{total_conds} conditions satisfied, "
                    f"state={state}, progress={progress}%")
        return SignalResult(
            template_id=template.id,
            state=state,
            groups=group_results,
            is_ready=all_ready,
            progress_percent=progress,
        )

    async def evaluate_groups(
        self,
        groups: list,
        logic: str,
        primary_tf: str,
        kline_data: dict[str, list[dict]],
        chan_data: dict[str, ChanResult],
        indicator_data: dict[str, dict[str, list[dict]]],
    ) -> bool:
        """评估一组条件组是否满足（用于条件式出场判断）。

        与 evaluate() 的区别：evaluate 返回详细的 SignalResult（含每个条件值，
        供信号面板展示），evaluate_groups 只返回布尔值（是否触发）。

        Args:
            groups: 条件组列表（复用 ConditionGroupSchema 结构）
            logic: 组间逻辑 "AND" / "OR"
            primary_tf: 主周期
            kline_data / chan_data / indicator_data: 各周期的数据

        Returns:
            True 表示条件组满足（触发），False 表示不满足
        """
        if not groups:
            return False

        group_results: list[bool] = []
        for group in groups:
            evaluations: list[bool] = []
            for cond in group.conditions:
                if not cond.enabled:
                    continue
                left_val = self._resolve(cond.left, cond, kline_data, chan_data, indicator_data, default_tf=primary_tf)
                right_val = self._resolve(cond.right, cond, kline_data, chan_data, indicator_data, default_tf=primary_tf)
                right2_val = self._resolve(cond.right2, cond, kline_data, chan_data, indicator_data, default_tf=primary_tf) if cond.right2 else None
                prev_left = self._resolve(cond.left, cond, kline_data, chan_data, indicator_data, offset=-1, default_tf=primary_tf)
                prev_right = self._resolve(cond.right, cond, kline_data, chan_data, indicator_data, offset=-1, default_tf=primary_tf)
                prev_prev_left = self._resolve(cond.left, cond, kline_data, chan_data, indicator_data, offset=-2, default_tf=primary_tf)
                evaluations.append(self._compare(
                    left_val, cond.operator, right_val, prev_left, prev_right, right2_val,
                    prev_prev_left=prev_prev_left,
                ))

            # 组内 AND：所有条件满足才算组满足
            group_results.append(all(evaluations) if evaluations else False)

        if logic == "AND":
            return all(group_results) if group_results else False
        return any(group_results) if group_results else False

    def _resolve(
        self, value, cond, kline_data, chan_data, indicator_data,
        offset: int = 0, default_tf: str = "1d", forced_tf: str | None = None,
    ) -> float:
        from app.schemas.signal import (
            PriceValue, IndicatorValue, ChanValue,
            ConstantValue, TimeframeValue,
        )

        if isinstance(value, TimeframeValue):
            return self._resolve(
                value.inner,
                cond,
                kline_data,
                chan_data,
                indicator_data,
                offset=offset,
                default_tf=default_tf,
                forced_tf=value.timeframe_id,
            )

        if isinstance(value, ConstantValue):
            return float(value.value)

        tf = forced_tf or cond.timeframe_id or default_tf

        if isinstance(value, PriceValue):
            klines = kline_data.get(tf, [])
            if not klines:
                return 0.0
            idx = -1 + offset
            if idx < -len(klines):
                return 0.0
            return float(klines[idx].get(value.field, 0))

        if isinstance(value, IndicatorValue):
            from app.services.signal_evaluation_service import indicator_data_key
            timeframe_indicators = indicator_data.get(tf, {})
            indicator_vals = timeframe_indicators.get(
                indicator_data_key(value.indicator_type, value.params),
                timeframe_indicators.get(value.indicator_type, []),
            )
            if not indicator_vals:
                return 0.0
            idx = -1 + offset
            if idx < -len(indicator_vals):
                return 0.0
            return float(indicator_vals[idx].get(value.field, 0))

        if isinstance(value, ChanValue):
            chan = chan_data.get(tf)
            if not chan:
                return 0.0
            if value.element == "buySellPoint":
                if value.property:
                    return float(sum(
                        1 for p in chan.buy_sell_points
                        if p.type == value.property
                    ))
                return float(len(chan.buy_sell_points))
            if value.element == "divergence":
                if value.property:
                    return float(sum(
                        1 for item in chan.divergences
                        if item.type == value.property and item.confirmed
                    ))
                return float(sum(1 for item in chan.divergences if item.confirmed))
            if value.element == "bi":
                return float(len(chan.bis))
            if value.element == "zhongshu":
                return float(len(chan.zhongshus))

        return 0.0

    def _compare(
        self,
        left: float,
        operator: str,
        right: float,
        prev_left: float = 0.0,
        prev_right: float = 0.0,
        right2: float | None = None,
        prev_prev_left: float = 0.0,
    ) -> bool:
        if operator == "gt":
            return left > right
        if operator == "gte":
            return left >= right
        if operator == "lt":
            return left < right
        if operator == "lte":
            return left <= right
        if operator == "eq":
            return abs(left - right) < 1e-8
        if operator == "between":
            if right2 is None:
                return False
            lower, upper = sorted((right, right2))
            return lower <= left <= upper
        if operator == "crossAbove":
            return prev_left <= prev_right and left > right
        if operator == "crossBelow":
            return prev_left >= prev_right and left < right
        if operator == "rising":
            return left > prev_left
        if operator == "falling":
            return left < prev_left
        if operator == "turnDown":
            return prev_left > prev_prev_left and left < prev_left
        if operator == "turnUp":
            return prev_left < prev_prev_left and left > prev_left
        return False
