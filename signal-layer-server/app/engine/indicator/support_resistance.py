"""压力位与支撑位（摆动枢轴 + ATR 缩放聚类）。

## 算法

两段式，与业内共识一致：

1. **摆动枢轴**：±`span` 根窗口的严格极值（见 `swings.py`）。枢轴位于 p，
   要到第 p+span 根才被确认，因此不存在"用未来数据定义当下位"的问题。
2. **聚类成位**：新确认的枢轴与已有位比较，距离在 `tolerance_atr × ATR` 之内
   且同向（高点→压力位、低点→支撑位）就并入（按触碰次数加权更新价位），
   否则新建一个位。容差用 **ATR 缩放**而不是固定百分比——固定百分比在波动率
   两端都会失效：低波动时把本该分开的位并成一个，高波动时同一个位被拆成多个。

维护规则：
- 位被触碰满 `min_touches` 次才**成立**（validated），才对外发布；
- 收盘价越过位超过一个容差视为**破位**：破位后角色互换（压力变支撑、支撑变
  压力）并重新计数，互换后再破一次则淘汰该位（只翻一次，避免来回抖动）；
- 长期无人触碰的位按时效过期。

## 输出契约（与 base.py 的约定一致）

- **决策字段**（在 `indicator.py` 的 `outputs` 白名单里）逐根因果：第 i 根的值只
  依赖 0..i 的数据，可直接用于条件与回测。
- **渲染字段** `level_1..level_N` **不在白名单里**，是"当前有效位"的快照：把最后
  一根仍在生效的位回填到它首次被触碰的位置，在图上画出水平线段。这样做的好处是
  每个槽位自始至终只属于一个位——槽位复用会把两个价位连成一条斜线——同时前端
  零改动（复用现有的 line plot 通道与 null 过滤），不需要新画布代码。
  代价是它不是因果序列，所以**绝不能进入条件字段**，这一点由 outputs 白名单保证。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from app.engine.indicator.base import (
    IndicatorCalculator,
    IndicatorResult,
    PlotSpec,
    RenderSpec,
    _atr,
    _get_closes,
    _get_highs,
    _get_lows,
    _get_times,
    _param_float,
    _param_int,
    register_indicator,
)
from app.engine.indicator.swings import swing_pivots

SUPPORT = "support"
RESISTANCE = "resistance"

# 支撑/压力的配色（同向多条线用深浅区分；未占用槽位用中性灰）
SUPPORT_COLORS = ("#2fc58d", "#57b98c", "#86ac8c")
RESISTANCE_COLORS = ("#ff5b62", "#dd7a80", "#bb969c")
UNUSED_COLOR = "#6b7280"


@dataclass
class _Level:
    """一个正在跟踪的支撑位或压力位。"""

    price: float
    role: str
    touches: int
    first_touch_bar: int
    last_touch_bar: int
    confirmed_bar: Optional[int] = None
    flipped: bool = False
    slot: Optional[int] = None

    @property
    def active(self) -> bool:
        """已在当前角色上成立。破位互换后 confirmed_bar 归零，要重新积累触碰。"""
        return self.confirmed_bar is not None


@register_indicator
class SupportResistanceCalculator(IndicatorCalculator):
    """用摆动枢轴聚类出压力位与支撑位。"""

    @property
    def type(self) -> str:
        return "support_resistance"

    def calculate(self, klines: list[dict], params: dict[str, Any]) -> IndicatorResult:
        normalized = self._params(params)
        span = int(normalized["span"])
        atr_len = int(normalized["atr_len"])
        tolerance_atr = float(normalized["tolerance_atr"])
        min_touches = int(normalized["min_touches"])
        touch_separation = int(normalized["touch_separation"])
        max_levels = int(normalized["max_levels"])
        max_age_bars = int(normalized["max_age_bars"])
        recency_half_life = int(normalized["recency_half_life"])

        times = _get_times(klines)
        highs = _get_highs(klines)
        lows = _get_lows(klines)
        closes = _get_closes(klines)
        atr = _atr(highs, lows, closes, atr_len)
        high_pivots, low_pivots = swing_pivots(highs, lows, span)

        values: list[dict[str, Any]] = [self._empty_row(timestamp) for timestamp in times]

        levels: list[_Level] = []
        for index in range(len(klines)):
            tolerance = self._tolerance(atr, index, tolerance_atr)
            broken: list[str] = []
            # ATR 未定义时不聚类：容差无从计算，硬给一个数会凭空造出位来
            if tolerance is not None:
                self._absorb_pivot(
                    levels, index, span, high_pivots, low_pivots, atr, tolerance_atr,
                    min_touches, touch_separation,
                )
                broken = self._break_levels(levels, index, closes[index], tolerance)
                self._expire_levels(levels, index, max_age_bars)

            self._fill_row(values[index], levels, closes[index], tolerance, broken)

        self._paint_level_lines(values, levels, max_levels, recency_half_life)

        return IndicatorResult(
            type=self.type,
            params=normalized,
            values=values,
            render=self._render(levels, max_levels),
        )

    # ── 参数与渲染规格 ──────────────────────────────────────────────────

    @staticmethod
    def _params(params: dict[str, Any]) -> dict[str, int | float]:
        normalized: dict[str, int | float] = {
            "span": _param_int(params, "span", 5),
            "atr_len": _param_int(params, "atr_len", 14),
            "tolerance_atr": _param_float(params, "tolerance_atr", 0.5),
            "min_touches": _param_int(params, "min_touches", 2),
            "touch_separation": _param_int(params, "touch_separation", 3),
            "max_levels": _param_int(params, "max_levels", 6),
            "max_age_bars": _param_int(params, "max_age_bars", 250),
            "recency_half_life": _param_int(params, "recency_half_life", 120),
        }
        if not 1 <= normalized["span"] <= 100:
            raise ValueError("摆动点窗口应在 1 到 100 之间")
        if not 2 <= normalized["atr_len"] <= 200:
            raise ValueError("ATR 周期应在 2 到 200 之间")
        if not 0 < normalized["tolerance_atr"] <= 20:
            raise ValueError("聚类容差倍数应大于0且不超过20")
        if not 1 <= normalized["min_touches"] <= 20:
            raise ValueError("成立所需触碰次数应在 1 到 20 之间")
        if not 0 <= normalized["touch_separation"] <= 100:
            raise ValueError("触碰间隔应在 0 到 100 之间")
        if not 1 <= normalized["max_levels"] <= 20:
            raise ValueError("同时显示的位置数应在 1 到 20 之间")
        if not 10 <= normalized["max_age_bars"] <= 5000:
            raise ValueError("位置最长存活根数应在 10 到 5000 之间")
        if not 10 <= normalized["recency_half_life"] <= 5000:
            raise ValueError("时间衰减半衰期应在 10 到 5000 之间")
        return normalized

    @staticmethod
    def _empty_row(timestamp: int) -> dict[str, Any]:
        return {
            "time": float(timestamp),
            "nearest_support": None,
            "nearest_resistance": None,
            "nearest_support_touches": None,
            "nearest_resistance_touches": None,
            "distance_to_support_pct": None,
            "distance_to_resistance_pct": None,
            "at_support": 0.0,
            "at_resistance": 0.0,
            "support_broken": 0.0,
            "resistance_broken": 0.0,
            "level_count": 0.0,
        }

    @staticmethod
    def _render(levels: list[_Level], max_levels: int) -> RenderSpec:
        """按槽位实际持有的角色上色（槽位在画线阶段才确定归属）。

        编号按**角色内**序号，而不是槽位号：否则会出现"压力位2"而实际只有
        一条压力线的情况，图例读起来像是少了一条。
        """
        role_by_slot = {level.slot: level.role for level in levels if level.slot is not None}
        role_counters = {SUPPORT: 0, RESISTANCE: 0}
        plots: list[PlotSpec] = []
        for slot in range(max_levels):
            role = role_by_slot.get(slot)
            if role is None:
                # 未占用的槽位给中性灰：默认成红色会让人以为那儿有个压力位
                plots.append(PlotSpec(
                    field=f"level_{slot + 1}", type="line",
                    color=UNUSED_COLOR, label=f"支撑/压力 {slot + 1}",
                ))
                continue
            role_counters[role] += 1
            palette = SUPPORT_COLORS if role == SUPPORT else RESISTANCE_COLORS
            label = "支撑位" if role == SUPPORT else "压力位"
            plots.append(PlotSpec(
                field=f"level_{slot + 1}",
                type="line",
                color=palette[slot % len(palette)],
                label=f"{label}{role_counters[role]}",
            ))
        return RenderSpec(window="main", plots=plots)

    # ── 聚类与维护 ──────────────────────────────────────────────────────

    @staticmethod
    def _tolerance(
        atr: list[Optional[float]], index: int, tolerance_atr: float,
    ) -> Optional[float]:
        value = atr[index] if index < len(atr) else None
        if value is None or value <= 0:
            return None
        return value * tolerance_atr

    def _absorb_pivot(
        self,
        levels: list[_Level],
        index: int,
        span: int,
        high_pivots: dict[int, float],
        low_pivots: dict[int, float],
        atr: list[Optional[float]],
        tolerance_atr: float,
        min_touches: int,
        touch_separation: int,
    ) -> None:
        """把本根刚确认的枢轴并入已有的位，或新建一个位。

        枢轴位于 index-span，容差取**枢轴那根**的 ATR：同一个枢轴无论何时被确认，
        聚类结果都一样，不会因为确认时刻的波动率变化而漂移。
        """
        pivot_bar = index - span
        if pivot_bar in high_pivots:
            price, role = high_pivots[pivot_bar], RESISTANCE
        elif pivot_bar in low_pivots:
            price, role = low_pivots[pivot_bar], SUPPORT
        else:
            return

        pivot_tolerance = self._tolerance(atr, pivot_bar, tolerance_atr)
        if pivot_tolerance is None:
            return

        nearest: Optional[_Level] = None
        for level in levels:
            if level.role != role:
                continue
            if abs(level.price - price) > pivot_tolerance:
                continue
            if nearest is None or abs(level.price - price) < abs(nearest.price - price):
                nearest = level

        if nearest is not None:
            # 同一根影线被反复计数会虚增触碰次数，太近的枢轴直接忽略
            if index - nearest.last_touch_bar < touch_separation:
                return
            nearest.price = (nearest.price * nearest.touches + price) / (nearest.touches + 1)
            nearest.touches += 1
            nearest.last_touch_bar = index
            if nearest.confirmed_bar is None and nearest.touches >= min_touches:
                nearest.confirmed_bar = index
            return

        levels.append(_Level(
            price=price,
            role=role,
            touches=1,
            first_touch_bar=index,
            last_touch_bar=index,
            confirmed_bar=index if min_touches <= 1 else None,
        ))

    @staticmethod
    def _break_levels(
        levels: list[_Level], index: int, close: float, tolerance: float,
    ) -> list[str]:
        """破位处理，返回本根被破的位的角色（用于当根信号）。

        收盘价越过位一个容差才算破位；只破一点影线不算。
        """
        broken_roles: list[str] = []
        retired: list[_Level] = []
        for level in levels:
            if not level.active:
                continue
            if level.role == SUPPORT:
                broken = close < level.price - tolerance
                flipped_role = RESISTANCE
            else:
                broken = close > level.price + tolerance
                flipped_role = SUPPORT
            if not broken:
                continue

            broken_roles.append(level.role)
            if level.flipped:
                # 互换过角色后又破一次 → 这个价位彻底失效
                retired.append(level)
                continue
            level.role = flipped_role
            level.flipped = True
            # 互换后在新角色上重新计数：它还是个候选位，要重新积累触碰
            level.touches = 1
            level.confirmed_bar = None
            level.first_touch_bar = index
            level.last_touch_bar = index

        for level in retired:
            levels.remove(level)
        return broken_roles

    @staticmethod
    def _expire_levels(levels: list[_Level], index: int, max_age_bars: int) -> None:
        levels[:] = [
            level for level in levels if index - level.last_touch_bar <= max_age_bars
        ]

    # ── 每根输出（因果） ────────────────────────────────────────────────

    @staticmethod
    def _fill_row(
        row: dict[str, Any],
        levels: list[_Level],
        close: float,
        tolerance: Optional[float],
        broken_roles: list[str],
    ) -> None:
        active = [level for level in levels if level.active]
        row["level_count"] = float(len(active))
        row["support_broken"] = 1.0 if SUPPORT in broken_roles else 0.0
        row["resistance_broken"] = 1.0 if RESISTANCE in broken_roles else 0.0

        # 最近支撑＝现价下方最高的那个支撑位；最近压力＝现价上方最低的那个压力位
        supports = [level for level in active if level.role == SUPPORT and level.price <= close]
        resistances = [level for level in active if level.role == RESISTANCE and level.price >= close]
        nearest_support = max(supports, key=lambda item: item.price, default=None)
        nearest_resistance = min(resistances, key=lambda item: item.price, default=None)

        if nearest_support is not None:
            row["nearest_support"] = round(nearest_support.price, 8)
            row["nearest_support_touches"] = float(nearest_support.touches)
            if close:
                row["distance_to_support_pct"] = round((close - nearest_support.price) / close * 100, 6)
            if tolerance is not None and abs(close - nearest_support.price) <= tolerance:
                row["at_support"] = 1.0
        if nearest_resistance is not None:
            row["nearest_resistance"] = round(nearest_resistance.price, 8)
            row["nearest_resistance_touches"] = float(nearest_resistance.touches)
            if close:
                row["distance_to_resistance_pct"] = round((nearest_resistance.price - close) / close * 100, 6)
            if tolerance is not None and abs(close - nearest_resistance.price) <= tolerance:
                row["at_resistance"] = 1.0

    # ── 渲染槽位（非因果，仅用于画线） ──────────────────────────────────

    @staticmethod
    def _paint_level_lines(
        values: list[dict[str, Any]],
        levels: list[_Level],
        max_levels: int,
        recency_half_life: int,
    ) -> None:
        """把**当前仍有效**的位画成水平线段。

        先按重要性排序再分配槽位：打分＝触碰次数 × 时间衰减（越近期被触碰越重要），
        同分时取更近期被触碰的那个。然后回填到各自首次被触碰的位置。

        只画仍在生效的位、且每个槽位只属于一个位，因此不会出现"槽位复用把两个
        价位连成斜线"。已破位/过期的历史位不画——它们已失效，画出来会误导。

        这些字段不在 outputs 白名单里，属渲染用途，因此允许这种非因果回填。
        """
        alive = [level for level in levels if level.active]
        if not alive or not values:
            return
        last_index = len(values) - 1

        def score(level: _Level) -> float:
            age = last_index - level.last_touch_bar
            decay = 0.5 ** (age / recency_half_life) if recency_half_life else 1.0
            return level.touches * decay

        ranked = sorted(alive, key=lambda item: (-score(item), -item.last_touch_bar))
        for slot, level in enumerate(ranked[:max_levels]):
            level.slot = slot
            field_name = f"level_{slot + 1}"
            for index in range(level.first_touch_bar, len(values)):
                values[index][field_name] = level.price
