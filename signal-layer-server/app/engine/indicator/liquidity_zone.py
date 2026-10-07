"""流动性聚集区：生成 → 聚集 → 被扫荡 → 消失 的时序过程。

## 生命周期（图上按时间段画方框）

```
生成 ──► 聚集 ──► 被扫荡（部分）──► 消失（完全扫荡）
实线框 + 填满      虚线框 + 填充递减（从被扫荡那侧抽空）──► 虚线框 + 不填充
```

图上的填充表示**流动性还在**：

- **生成**：同向摆动枢轴的第一个枢轴落下，区带出现（尚未成立），画出实线框。
- **聚集**：后续同向枢轴落进 `eq_atr × ATR` 容差内，触碰次数累加，达到
  `min_touches` 后成立。生成与聚集这两段都是**实线框 + 填满**。
- **被扫荡**：影线越过区带边缘 pierce 以上 → 该区**立刻退出有效集合**
  （"被扫荡后聚集区就不存在了"），方框转为**虚线**，填充按剩余比例递减
  （从被扫荡的那一侧开始抽空）。
- **消失**：被消耗比例达到 1（价格走完整个区带）→ 填充为 0，只剩虚线边框，
  作为历史保留到破位或过期。

方框**按时间段限制**：左边界＝生成处，右边界＝被扫荡那一刻，之后定格不再向右
延伸——这正是"扫荡之后它就不存在了"在时间轴上的表达。尚未被扫荡的区一直延伸
到最后一根。

## 被消耗比例的口径

`consumed = 越界幅度 ÷ 区带高度`，上限 1：

- 上沿被扫荡（等高区，流动性在上方）：`(最高价 - 区带上沿) / (上沿 - 下沿)`
- 下沿被扫荡（等低区）：`(区带下沿 - 最低价) / (上沿 - 下沿)`

即"越过边缘越多，被拿走的越多"：浅浅一刺只拿走边缘附近的挂单，深刺把整条流动性
清掉（比例到 1 即完全扫荡）。图上的**填充比例 = 1 - consumed**，也就是"还剩多少"。
**这个口径是替你定的**——另一种可选口径是"被扫荡的触碰次数 ÷ 总触碰次数"，
但那样新枢轴加入会让已有百分比回落、看起来自相矛盾，所以选了与几何幅度挂钩的口径。

## 与 liquidity_sweep 的关系

两者都基于"越过水平后收盘回到内侧"的扫荡语义，但 `liquidity_sweep` 关心
"刚才有没有扫荡信号"（单点水平 + 入场过滤），本指标关心"流动性堆在哪、被拿走
多少"。共用摆动枢轴（`swings.py`）与 ATR（`base._atr`）两层基础设施。

## 输出契约（与 base.py 的约定一致）

- **决策字段**（`indicator.py` 的 outputs 白名单）逐根因果，只描述**当前仍在聚集
  阶段**（尚未被扫荡）的聚集区。
- **渲染字段** `zone_{k}_low/high/consumed/swept/swept_from_top` 不在白名单里：
  每槽位一套独立字段，因此并发区互不覆盖（前端那套按 zone_id 单列分组的画法做不到）。
  这些字段是"最后一根时的样子"回填到历史，不是因果序列。
  前端按这套约定还原方框，填充比例自己算成 `1 - consumed`（还剩多少流动性）。
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

EQ_HIGH = "eqh"
EQ_LOW = "eql"
UP = "up"
DOWN = "down"

# 仍在聚集＝实线蓝框、已被扫荡＝虚线紫框（与帝论区间带的成熟态配色同系）
ACTIVE_COLOR = "#6c8cff"
SWEPT_COLOR = "#9b8cf2"
UNUSED_COLOR = "#6b7280"


@dataclass
class _Zone:
    """一个等高等低形成的流动性聚集区，带生命周期状态。"""

    level: float
    low: float
    high: float
    kind: str
    touches: int
    first_bar: int
    last_touch_bar: int
    confirmed_bar: Optional[int] = None
    # 被消耗比例 0..1（越界幅度 / 区带高度）；> 0 表示流动性已被拿走一部分
    consumed_ratio: float = 0.0
    consumed_from_top: bool = False
    # 是否已越过 pierce 门槛（噪声过滤）：一旦越过就退出有效集合
    penetrated: bool = False
    penetrated_bar: Optional[int] = None
    swept: bool = False
    swept_bar: Optional[int] = None
    swept_side: Optional[str] = None
    pending_bar: Optional[int] = None
    outside_streak: int = 0

    @property
    def validated(self) -> bool:
        """触碰次数够了，是一个正经的聚集区。"""
        return self.confirmed_bar is not None

    @property
    def active(self) -> bool:
        """仍在"聚集"阶段、可作为流动性目标的区（决策字段只认这些）。"""
        return self.validated and not self.penetrated

    @property
    def gone(self) -> bool:
        """流动性被完全拿走。"""
        return self.consumed_ratio >= 1.0

    @property
    def band_height(self) -> float:
        return self.high - self.low

    def end_bar(self, last_index: int) -> int:
        """方框右边界：被扫荡时定格在那一刻，否则延伸到最后一根。"""
        return self.penetrated_bar if self.penetrated_bar is not None else last_index


@register_indicator
class LiquidityZoneCalculator(IndicatorCalculator):
    """识别流动性聚集区，并跟踪它的生成、聚集、被扫荡与消失。"""

    @property
    def type(self) -> str:
        return "liquidity_zone"

    def calculate(self, klines: list[dict], params: dict[str, Any]) -> IndicatorResult:
        normalized = self._params(params)
        span = int(normalized["span"])
        atr_len = int(normalized["atr_len"])
        eq_atr = float(normalized["eq_atr"])
        min_touches = int(normalized["min_touches"])
        zone_width_atr = float(normalized["zone_width_atr"])
        pierce_atr = float(normalized["pierce_atr"])
        reclaim_bars = int(normalized["reclaim_bars"])
        break_bars = int(normalized["break_bars"])
        max_age_bars = int(normalized["max_age_bars"])
        max_zones = int(normalized["max_zones"])

        times = _get_times(klines)
        highs = _get_highs(klines)
        lows = _get_lows(klines)
        closes = _get_closes(klines)
        atr = _atr(highs, lows, closes, atr_len)
        high_pivots, low_pivots = swing_pivots(highs, lows, span)

        values: list[dict[str, Any]] = [self._empty_row(timestamp) for timestamp in times]

        zones: list[_Zone] = []
        for index in range(len(klines)):
            bar_atr = atr[index] if index < len(atr) else None
            swept_events: list[str] = []
            broken = 0.0
            # 波动率未知时不建区：容差与带厚都无从计算
            if bar_atr is not None and bar_atr > 0:
                self._absorb_pivot(
                    zones, index, span, high_pivots, low_pivots, atr,
                    eq_atr, zone_width_atr, min_touches,
                )
                swept_events, broken = self._advance(
                    zones, index, highs[index], lows[index], closes[index],
                    bar_atr * pierce_atr, reclaim_bars, break_bars,
                )
                self._expire(zones, index, max_age_bars)

            self._fill_row(
                values[index], zones, closes[index],
                bar_atr * pierce_atr if bar_atr else None, swept_events, broken,
            )

        # 画框与渲染规格必须用同一份槽位分配，否则颜色/图例会与实际的区对不上
        slot_zones = self._paint_boxes(values, zones, closes[-1] if closes else 0.0, max_zones)

        return IndicatorResult(
            type=self.type,
            params=normalized,
            values=values,
            render=self._render(slot_zones, max_zones),
        )

    # ── 参数与渲染规格 ──────────────────────────────────────────────────

    @staticmethod
    def _params(params: dict[str, Any]) -> dict[str, int | float]:
        normalized: dict[str, int | float] = {
            "span": _param_int(params, "span", 5),
            "atr_len": _param_int(params, "atr_len", 14),
            "eq_atr": _param_float(params, "eq_atr", 0.35),
            "min_touches": _param_int(params, "min_touches", 2),
            "zone_width_atr": _param_float(params, "zone_width_atr", 0.5),
            "pierce_atr": _param_float(params, "pierce_atr", 0.15),
            "reclaim_bars": _param_int(params, "reclaim_bars", 3),
            "break_bars": _param_int(params, "break_bars", 2),
            "max_age_bars": _param_int(params, "max_age_bars", 250),
            "max_zones": _param_int(params, "max_zones", 4),
        }
        if not 1 <= normalized["span"] <= 100:
            raise ValueError("摆动点窗口应在 1 到 100 之间")
        if not 2 <= normalized["atr_len"] <= 200:
            raise ValueError("ATR 周期应在 2 到 200 之间")
        if not 0 < normalized["eq_atr"] <= 20:
            raise ValueError("等高容差倍数应大于0且不超过20")
        if not 1 <= normalized["min_touches"] <= 20:
            raise ValueError("成区所需触碰次数应在 1 到 20 之间")
        if not 0 < normalized["zone_width_atr"] <= 20:
            raise ValueError("区带厚度倍数应大于0且不超过20")
        if not 0 <= normalized["pierce_atr"] <= 20:
            raise ValueError("穿透判定倍数应在 0 到 20 之间")
        if not 1 <= normalized["reclaim_bars"] <= 100:
            raise ValueError("回收窗口应在 1 到 100 之间")
        if not 1 <= normalized["break_bars"] <= 100:
            raise ValueError("破位确认根数应在 1 到 100 之间")
        if not 10 <= normalized["max_age_bars"] <= 5000:
            raise ValueError("区最长存活根数应在 10 到 5000 之间")
        if not 1 <= normalized["max_zones"] <= 20:
            raise ValueError("同时显示的区数量应在 1 到 20 之间")
        return normalized

    @staticmethod
    def _empty_row(timestamp: int) -> dict[str, Any]:
        return {
            "time": float(timestamp),
            "zone_count": 0.0,
            "nearest_zone_low": None,
            "nearest_zone_high": None,
            "nearest_zone_touches": None,
            "nearest_zone_swept": None,
            "nearest_zone_consumed_pct": None,
            "price_in_zone": 0.0,
            "distance_to_zone_pct": None,
            "sweep_up": 0.0,
            "sweep_down": 0.0,
            "zone_broken": 0.0,
        }

    @staticmethod
    def _render(slot_zones: list[Optional[_Zone]], max_zones: int) -> RenderSpec:
        """每槽位一个方框规格；实线/虚线、填充多少由前端按 region 数据决定。

        字段约定（前端 zoneBoxes 按这套约定取兄弟字段，契约测试会校验它存在）：
        `zone_{k}_low` / `zone_{k}_high` / `zone_{k}_consumed` / `zone_{k}_swept`
        / `zone_{k}_swept_from_top`
        """
        plots: list[PlotSpec] = []
        for slot in range(max_zones):
            zone = slot_zones[slot] if slot < len(slot_zones) else None
            if zone is None:
                color, label = UNUSED_COLOR, f"聚集区 {slot + 1}"
            elif zone.penetrated:
                color = SWEPT_COLOR
                label = f"聚集区{slot + 1}（已扫荡 {int(round(zone.consumed_ratio * 100))}%）"
            elif not zone.validated:
                color, label = ACTIVE_COLOR, f"聚集区{slot + 1}（生成中）"
            else:
                color, label = ACTIVE_COLOR, f"聚集区{slot + 1}（聚集 {zone.touches} 触）"
            plots.append(PlotSpec(
                field=f"zone_{slot + 1}_low", type="zone", color=color, label=label,
            ))
        return RenderSpec(window="main", plots=plots)

    # ── 聚区 ────────────────────────────────────────────────────────────

    def _absorb_pivot(
        self,
        zones: list[_Zone],
        index: int,
        span: int,
        high_pivots: dict[int, float],
        low_pivots: dict[int, float],
        atr: list[Optional[float]],
        eq_atr: float,
        zone_width_atr: float,
        min_touches: int,
    ) -> None:
        """把本根刚确认的枢轴并入已有的等高/等低区，或新建一个区。"""
        pivot_bar = index - span
        if pivot_bar in high_pivots:
            price, kind = high_pivots[pivot_bar], EQ_HIGH
        elif pivot_bar in low_pivots:
            price, kind = low_pivots[pivot_bar], EQ_LOW
        else:
            return

        pivot_atr = atr[pivot_bar] if pivot_bar < len(atr) else None
        # 容差取枢轴那根的 ATR：同一枢轴无论何时确认，聚合结果都一致
        if pivot_atr is None or pivot_atr <= 0:
            return
        tolerance = pivot_atr * eq_atr
        half_width = pivot_atr * zone_width_atr / 2

        nearest: Optional[_Zone] = None
        for zone in zones:
            if zone.kind != kind:
                continue
            if abs(zone.level - price) > tolerance:
                continue
            if nearest is None or abs(zone.level - price) < abs(nearest.level - price):
                nearest = zone

        if nearest is not None:
            nearest.level = (nearest.level * nearest.touches + price) / (nearest.touches + 1)
            nearest.touches += 1
            nearest.last_touch_bar = index
            nearest.low = nearest.level - half_width
            nearest.high = nearest.level + half_width
            if nearest.confirmed_bar is None and nearest.touches >= min_touches:
                nearest.confirmed_bar = index
            return

        zones.append(_Zone(
            level=price,
            low=price - half_width,
            high=price + half_width,
            kind=kind,
            touches=1,
            first_bar=index,
            last_touch_bar=index,
            confirmed_bar=index if min_touches <= 1 else None,
        ))

    # ── 生命周期推进 ────────────────────────────────────────────────────

    @staticmethod
    def _advance(
        zones: list[_Zone],
        index: int,
        high: float,
        low: float,
        close: float,
        pierce: float,
        reclaim_bars: int,
        break_bars: int,
    ) -> tuple[list[str], float]:
        """逐区推进"聚集 → 被扫荡 → 消失"以及破位退役。

        两侧不对称，这是关键：**等高区**的流动性在**上沿**（上方挂着突破单与
        空头止损），只看上方的越界；价格往回跌与这个区无关，不能算破位。
        **等低区**镜像。

        返回 (本根完成的扫荡方向列表, 本根退役标记)。
        """
        swept_events: list[str] = []
        retired: list[_Zone] = []
        for zone in zones:
            if not zone.validated:
                continue

            band = zone.band_height
            if band > 0:
                if zone.kind == EQ_HIGH:
                    excursion, from_top = high - zone.high, True
                else:
                    excursion, from_top = zone.low - low, False
                if excursion > 0:
                    # 被消耗比例 = 越界幅度 / 区带高度（上限 1），取历史最大
                    ratio = min(excursion / band, 1.0)
                    if ratio > zone.consumed_ratio:
                        zone.consumed_ratio = ratio
                        zone.consumed_from_top = from_top
                if excursion > pierce and not zone.penetrated:
                    # 越过噪声门槛 → 退出有效集合，方框在此定格并转为虚线
                    zone.penetrated = True
                    zone.penetrated_bar = index

            if zone.kind == EQ_HIGH:
                pierced = high > zone.high + pierce
                reclaimed = close <= zone.high
                side = UP
            else:
                pierced = low < zone.low - pierce
                reclaimed = close >= zone.low
                side = DOWN

            # 穿透登记：只有越过边缘 pierce 以上才算，避免把噪声当扫荡
            if zone.pending_bar is None and pierced:
                zone.pending_bar = index
            if zone.pending_bar is not None:
                if reclaimed:
                    # 影线越界后收盘回到内侧 → 流动性被扫荡。同根就收回
                    # （Wick Only）也在此判定：这类扫荡当天完成，推迟一根报会平白慢一根。
                    zone.swept = True
                    zone.swept_bar = index
                    zone.swept_side = side
                    swept_events.append(side)
                    zone.pending_bar = None
                elif index - zone.pending_bar > reclaim_bars:
                    # 窗口内没收回，这次穿透不再算扫荡
                    zone.pending_bar = None

            # 破位：连续收在该区外侧（方向由 kind 决定）
            if close > zone.high if zone.kind == EQ_HIGH else close < zone.low:
                zone.outside_streak += 1
            else:
                zone.outside_streak = 0
            if zone.outside_streak >= break_bars:
                retired.append(zone)

        for zone in retired:
            zones.remove(zone)
        return swept_events, 1.0 if retired else 0.0

    @staticmethod
    def _expire(zones: list[_Zone], index: int, max_age_bars: int) -> None:
        zones[:] = [zone for zone in zones if index - zone.last_touch_bar <= max_age_bars]

    # ── 每根输出（因果） ────────────────────────────────────────────────

    @staticmethod
    def _fill_row(
        row: dict[str, Any],
        zones: list[_Zone],
        close: float,
        pierce: Optional[float],
        swept_events: list[str],
        broken: float,
    ) -> None:
        # 决策字段只描述仍在聚集阶段（尚未被扫荡）的区
        active = [zone for zone in zones if zone.active]
        row["zone_count"] = float(len(active))
        row["sweep_up"] = 1.0 if UP in swept_events else 0.0
        row["sweep_down"] = 1.0 if DOWN in swept_events else 0.0
        row["zone_broken"] = broken
        if not active:
            return

        def distance(zone: _Zone) -> float:
            if zone.low <= close <= zone.high:
                return 0.0
            return min(abs(close - zone.low), abs(close - zone.high))

        nearest = min(active, key=distance)
        row["nearest_zone_low"] = round(nearest.low, 8)
        row["nearest_zone_high"] = round(nearest.high, 8)
        row["nearest_zone_touches"] = float(nearest.touches)
        row["nearest_zone_swept"] = 0.0
        row["nearest_zone_consumed_pct"] = round(nearest.consumed_ratio * 100, 6)
        row["price_in_zone"] = 1.0 if nearest.low <= close <= nearest.high else 0.0
        if close:
            row["distance_to_zone_pct"] = round(distance(nearest) / close * 100, 6)

    # ── 渲染槽位（非因果，仅用于画方框） ────────────────────────────────

    @staticmethod
    def _paint_boxes(
        values: list[dict[str, Any]],
        zones: list[_Zone],
        last_close: float,
        max_zones: int,
    ) -> list[Optional[_Zone]]:
        """把每个区画成一个"按时间段限制"的方框。

        从**生成**（第一个枢轴）起就画——生成与聚集都是实线框 + 填满，被扫荡后
        转虚线并抽空填充。每个槽位一套独立字段，因此并发区互不覆盖。右边界由
        `end_bar` 决定：被扫荡的区定格在扫荡那一刻（之后不再向右延伸），
        仍在聚集的区延伸到最后一根。

        排序（否则历史与候选会把真正有效的区挤出画面）：
        1. 仍在聚集的区 —— 按离现价的距离；
        2. 已被扫荡的区 —— 按扫荡时间由近及远。"扫荡后不填充"是这块要传达的信息，
           它必须比"生成中的候选"更优先；
        3. 生成中的候选区 —— 按离现价的距离。它只是候选，最容易被挤掉。

        这些字段不在 outputs 白名单里，属渲染用途，因此允许这种非因果回填。
        """
        candidates = list(zones)
        if not candidates or not values:
            return []

        def rank_key(zone: _Zone) -> tuple[int, float, int]:
            distance = min(abs(last_close - zone.low), abs(last_close - zone.high))
            if zone.active:
                return 0, distance, 0
            if zone.penetrated:
                return 1, 0.0, -(zone.penetrated_bar or 0)
            return 2, distance, 0

        ranked = sorted(candidates, key=rank_key)[:max_zones]
        slots: list[Optional[_Zone]] = [None] * max_zones
        last_index = len(values) - 1
        for slot, zone in enumerate(ranked):
            slots[slot] = zone
            low_field, high_field = f"zone_{slot + 1}_low", f"zone_{slot + 1}_high"
            consumed_field = f"zone_{slot + 1}_consumed"
            swept_field = f"zone_{slot + 1}_swept"
            from_top_field = f"zone_{slot + 1}_swept_from_top"
            for index in range(zone.first_bar, min(zone.end_bar(last_index), last_index) + 1):
                row = values[index]
                row[low_field] = round(zone.low, 8)
                row[high_field] = round(zone.high, 8)
                row[consumed_field] = round(zone.consumed_ratio, 6)
                row[swept_field] = 1.0 if zone.penetrated else 0.0
                row[from_top_field] = 1.0 if zone.consumed_from_top else 0.0
        return slots
