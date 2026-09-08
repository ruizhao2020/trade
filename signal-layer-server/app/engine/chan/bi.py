"""
============================================================================
笔检测 — 完全对齐 czsc 算法 (crates/czsc-core/src/analyze/utils.rs)
============================================================================

## czsc 算法核心规则 (check_bi)

### 输入
- bars_ubi: 去包含关系后的 K 线列表(NewBar)
- min_bi_len: 笔的最小长度(去包含后的 K 线根数),czsc 默认 6

### 算法步骤
1. 在 bars_ubi 上调用 check_fxs 获取所有分型
2. 取第一个分型 fx_a 作为笔的起点
3. 根据 fx_a.mark 确定笔的方向:
   - fx_a 是底分型(D) → 向上笔,找 fx_b(顶分型,且 fx_b.fx > fx_a.fx,取 high 最大的)
   - fx_a 是顶分型(G) → 向下笔,找 fx_b(底分型,且 fx_b.fx < fx_a.fx,取 low 最小的)
4. 检查成笔条件:
   - fx_a 和 fx_b 之间无包含关系
   - bars_a(从 fx_a.elements[0] 到 fx_b.elements[2])长度 >= min_bi_len
5. 笔的 bars = bars_a(从 fx_a 第一根 K 线到 fx_b 第三根 K 线)

### czsc 默认 min_bi_len = 6
对应 Rust 代码: resolve_min_bi_len() 默认值 6
(旧简化版用的是 5,博客文章说的也是 5,但 czsc 最新源码是 6)
"""

from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Literal
from app.engine.chan.merge import NewBar
from app.engine.chan.fenxing import Fenxing, check_fxs

logger = logging.getLogger(__name__)

# czsc 默认值: 笔的最小长度(去包含后的 K 线根数)
# 对应 Rust: resolve_min_bi_len() 默认 6
CZSC_MIN_BI_LEN = 6


@dataclass
class Bi:
    """
    笔的数据结构(对齐 czsc 的 BI)。

    direction: "up"=向上笔, "down"=向下笔
    fx_a: 起始分型
    fx_b: 结束分型
    bars: 构成笔的 NewBar 列表
    high/low: 笔的高低点(对应 czsc BI.get_high/get_low = max(fx_a.high, fx_b.high))
    power: 价差力度(对应 czsc BI.get_power_price = |fx_b.fx - fx_a.fx|)
    """
    index: int
    direction: Literal["up", "down"]
    fx_a: Fenxing | None
    fx_b: Fenxing | None
    bars: list[NewBar]
    high: float
    low: float
    # 兼容旧接口的字段
    start_time: int
    end_time: int
    start_price: float
    end_price: float
    power: float
    fenxing_start: int | None = None
    fenxing_end: int | None = None
    merged_span: int = 0


def check_bi(bars_ubi: list[NewBar], min_bi_len: int = CZSC_MIN_BI_LEN) -> tuple[Bi | None, list[NewBar]]:
    """
    查找一笔 — 完全对齐 czsc check_bi 函数。

    Args:
        bars_ubi: 去包含关系后的 K 线列表
        min_bi_len: 笔的最小长度(去包含 K 线根数),默认 6

    Returns:
        (bi, remaining_bars):
            bi: 找到的第一笔,或 None
            remaining_bars: 找到笔后剩余的 K 线(从 fx_b.elements[0] 开始),用于找下一笔
    """
    fxs = check_fxs(bars_ubi)
    if len(fxs) < 2:
        return (None, bars_ubi)

    fx_a = fxs[0]

    # 根据 fx_a 类型确定方向和 fx_b
    # 对齐 czsc check_bi 原始实现:取极值(向上笔取 high 最大的顶分型,向下笔取 low 最小的底分型)
    if fx_a.direction == "bottom":
        # 底分型 → 向上笔,找顶分型 fx_b(fx > fx_a.fx,取 high 最大的)
        direction: Literal["up", "down"] = "up"
        fx_b = None
        for x in fxs:
            if x.direction == "top" and x.merged_kline.dt > fx_a.merged_kline.dt and x.price > fx_a.price:
                if fx_b is None or x.merged_kline.high > fx_b.merged_kline.high:
                    fx_b = x
    else:
        # 顶分型 → 向下笔,找底分型 fx_b(fx < fx_a.fx,取 low 最小的)
        direction = "down"
        fx_b = None
        for x in fxs:
            if x.direction == "bottom" and x.merged_kline.dt > fx_a.merged_kline.dt and x.price < fx_a.price:
                if fx_b is None or x.merged_kline.low < fx_b.merged_kline.low:
                    fx_b = x

    if fx_b is None:
        return (None, bars_ubi)

    # 确定 bars_a 的起始和结束(对齐 czsc: 用 dt 过滤,而非索引切片)
    # czsc: start_dt = fx_a.elements[0].dt, end_dt = fx_b.elements[2].dt
    start_idx = fx_a.elements[0]  # 存的是索引,需取对应 NewBar 的 dt
    end_idx = fx_b.elements[2]
    # elements 存的是 bars_ubi 的索引,取对应 NewBar 的 dt
    if start_idx >= len(bars_ubi) or end_idx >= len(bars_ubi):
        return (None, bars_ubi)
    start_dt_val = bars_ubi[start_idx].dt
    end_dt_val = bars_ubi[end_idx].dt

    # 用 dt 过滤(对齐 czsc partition_point)
    bars_a = [b for b in bars_ubi if start_dt_val <= b.dt <= end_dt_val]
    if len(bars_a) < 2:
        return (None, bars_ubi)

    # 确定剩余 bars_b(从 fx_b.elements[0] 对应的 dt 开始)
    new_start_dt_idx = fx_b.elements[0]
    if new_start_dt_idx >= len(bars_ubi):
        return (None, bars_ubi)
    new_start_dt_val = bars_ubi[new_start_dt_idx].dt
    bars_b = [b for b in bars_ubi if b.dt >= new_start_dt_val]

    # 判断 fx_a 和 fx_b 之间的包含关系
    # czsc: ab_include = (fx_a.high > fx_b.high && fx_a.low < fx_b.low) || (fx_a.high < fx_b.high && fx_a.low > fx_b.low)
    ab_include = (
        (fx_a.merged_kline.high > fx_b.merged_kline.high and fx_a.merged_kline.low < fx_b.merged_kline.low)
        or (fx_a.merged_kline.high < fx_b.merged_kline.high and fx_a.merged_kline.low > fx_b.merged_kline.low)
    )

    # 检查成笔条件: 无包含关系 且 长度足够
    if not ab_include and len(bars_a) >= min_bi_len:
        # 笔的高低点(对齐 czsc BI.get_high/get_low)
        high = max(fx_a.merged_kline.high, fx_b.merged_kline.high)
        low = min(fx_a.merged_kline.low, fx_b.merged_kline.low)
        # 价差力度(对齐 czsc BI.get_power_price)
        power = abs(fx_b.price - fx_a.price)

        bi = Bi(
            index=0,
            direction=direction,
            fx_a=fx_a,
            fx_b=fx_b,
            bars=list(bars_a),
            high=high,
            low=low,
            start_time=fx_a.merged_kline.dt,
            end_time=fx_b.merged_kline.dt,
            start_price=fx_a.price,
            end_price=fx_b.price,
            power=power,
            fenxing_start=fx_a.index,
            fenxing_end=fx_b.index,
            merged_span=fx_b.merged_index - fx_a.merged_index,
        )
        return (bi, list(bars_b))
    else:
        return (None, bars_ubi)


def build_bis_from_bars(bars_ubi: list[NewBar], min_bi_len: int = CZSC_MIN_BI_LEN) -> list[Bi]:
    """
    构建笔 — 逐根增量模拟 czsc CZSC::__update_bi 的完整逻辑(含回滚)。

    czsc 是逐根 K 线调用 update_bar → __update_bi:
    1. 在当前已到达的 bars_ubi 上找笔(只看过去,不看未来)
    2. 找到笔后,检查最后一笔是否被当前 K 线破坏,若破坏则回滚

    回滚逻辑(对齐 czsc crates/czsc-core/src/analyze/mod.rs L284-303):
    - merge_point = last_bi.bars[len-2].dt
    - bars_ubi = last_bi.bars[:-2] + [b for b in bars_ubi if b.dt >= merge_point]
    - bi_list.pop()

    Args:
        bars_ubi: 去包含关系后的 K 线列表
        min_bi_len: 笔的最小长度,默认 7

    Returns:
        list[Bi]: 笔列表(顶底交替,方向交替)
    """
    if len(bars_ubi) < 3:
        logger.info(f"build_bis_from_bars: {len(bars_ubi)} bars (need >=3) -> 0 bis")
        return []

    bis: list[Bi] = []
    bars_ubi_state: list[NewBar] = []

    for new_bar in bars_ubi:
        bars_ubi_state.append(new_bar)
        if len(bars_ubi_state) < 3:
            continue

        # === 找笔(对齐 czsc __update_bi)===
        if not bis:
            # 第一笔:fx_a 取同向分型中极值最优的(对齐 czsc __update_bi 第一笔逻辑)
            fxs = check_fxs(bars_ubi_state)
            if not fxs:
                continue
            first = fxs[0]
            fx_a = first
            for x in fxs:
                if x.direction == first.direction:
                    if first.direction == "bottom" and x.price <= fx_a.price:
                        fx_a = x
                    elif first.direction == "top" and x.price >= fx_a.price:
                        fx_a = x
            start_idx = fx_a.elements[0]
            if start_idx < len(bars_ubi_state):
                start_dt = bars_ubi_state[start_idx].dt
                filtered = [b for b in bars_ubi_state if b.dt >= start_dt]
            else:
                filtered = bars_ubi_state
            bi, bars_ubi_new = check_bi(filtered, min_bi_len)
            if bi is not None:
                bi.index = len(bis)
                bis.append(bi)
                bars_ubi_state = bars_ubi_new
        else:
            # 后续笔:直接 check_bi(bars_ubi_state),fx_a = fxs[0](对齐 czsc)
            bi, bars_ubi_new = check_bi(bars_ubi_state, min_bi_len)
            if bi is not None:
                bi.index = len(bis)
                bis.append(bi)
                bars_ubi_state = bars_ubi_new

        # === 回滚检查(对齐 czsc __update_bi L284-303)===
        # 最后一笔被当前 K 线破坏 → 回滚
        if bars_ubi_state and bis:
            last_bi = bis[-1]
            last_bar = bars_ubi_state[-1]
            destroyed = (
                (last_bi.direction == "up" and last_bar.high > last_bi.high)
                or (last_bi.direction == "down" and last_bar.low < last_bi.low)
            )
            if destroyed and len(last_bi.bars) >= 2:
                # czsc: merge_point = last_bi.bars[len-2].dt
                merge_point_dt = last_bi.bars[-2].dt
                # czsc: bars_ubi = last_bi.bars[:-2] + bars_ubi.filter(dt >= merge_point)
                # 注意:用 dt 去重,避免 merge_point 附近的 K 线重复
                before_merge = [b for b in last_bi.bars[:-2] if b.dt < merge_point_dt]
                at_or_after = [b for b in bars_ubi_state if b.dt >= merge_point_dt]
                bars_ubi_state = before_merge + at_or_after
                bis.pop()

    logger.info(f"build_bis_from_bars: {len(bars_ubi)} bars -> {len(bis)} bis (czsc algorithm, min_bi_len={min_bi_len})")
    return bis


def build_bis(fenxings: list[Fenxing]) -> list[Bi]:
    """
    兼容旧接口: 从分型列表构建笔。

    注意:此接口无法严格对齐 czsc 算法,因为 czsc 是在 bars_ubi 上找笔,
    而此接口只有分型列表(丢失了 K 线信息,无法检查 min_bi_len 和包含关系)。
    建议新代码使用 build_bis_from_bars(get_bars_ubi(raw_klines))。

    此兼容接口采用简化逻辑: 顶底交替的分型直接连成笔。
    """
    if len(fenxings) < 2:
        logger.info(f"build_bis (legacy): {len(fenxings)} fenxings -> 0 bis")
        return []

    bis: list[Bi] = []
    for i in range(1, len(fenxings)):
        fx_a = fenxings[i - 1]
        fx_b = fenxings[i]

        if fx_a.direction == fx_b.direction:
            continue

        if fx_a.direction == "bottom" and fx_b.direction == "top":
            direction: Literal["up", "down"] = "up"
        else:
            direction = "down"

        high = max(fx_a.merged_kline.high, fx_b.merged_kline.high)
        low = min(fx_a.merged_kline.low, fx_b.merged_kline.low)
        power = abs(fx_b.price - fx_a.price)

        bis.append(Bi(
            index=len(bis),
            direction=direction,
            fx_a=fx_a,
            fx_b=fx_b,
            bars=[],  # 旧接口无 bars 信息
            high=high,
            low=low,
            start_time=fx_a.merged_kline.dt,
            end_time=fx_b.merged_kline.dt,
            start_price=fx_a.price,
            end_price=fx_b.price,
            power=power,
            fenxing_start=fx_a.index,
            fenxing_end=fx_b.index,
            merged_span=fx_b.merged_index - fx_a.merged_index,
        ))

    logger.info(f"build_bis (legacy): {len(fenxings)} fenxings -> {len(bis)} bis")
    return bis
