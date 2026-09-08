"""
============================================================================
K 线包含关系处理 — 完全对齐 czsc 算法 (crates/czsc-core/src/analyze/utils.rs)
============================================================================

## czsc 算法核心规则
1. 通过比较 k1.high 和 k2.high 确定方向:
   - k1.high < k2.high → direction = Up
   - k1.high > k2.high → direction = Down
   - 相等 → 不合并,k3 作为新 K 线
2. 判断 k2 与 k3 是否存在包含关系:
   - (k2.high <= k3.high 且 k2.low >= k3.low) 或 (k2.high >= k3.high 且 k2.low <= k3.low)
3. 如有包含,按方向合并:
   - Up: high = max(k2.high, k3.high), low = max(k2.low, k3.low)
   - Down: high = min(k2.high, k3.high), low = min(k2.low, k3.low)
4. dt 取被保留极值所在 K 线的时间

## 与 czsc Rust 版的差异
- czsc 是增量更新(update_bar),逐根处理
- 本实现是批量模式,一次处理所有 K 线,结果与 czsc 增量模式等价
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class NewBar:
    """
    去包含关系后的 K 线(对应 czsc 的 NewBar)。

    elements 记录被合并的原始 K 线索引列表(对应 czsc 的 NewBar.elements)。
    dt 取极值所在 K 线的时间(对应 czsc 的合并规则)。
    """
    dt: int                # K 线时间(秒级或毫秒级,与输入一致)
    open: float
    close: float
    high: float
    low: float
    vol: float = 0.0
    amount: float = 0.0
    elements: list[int] = field(default_factory=list)  # 被合并的原始 K 线索引


@dataclass
class MergedKLine:
    """兼容旧接口的合并 K 线数据结构"""
    open_time: int
    high: float
    low: float
    raw_indices: list[int] = field(default_factory=list)
    merged_count: int = 1


def _new_bar_from_raw(kline: dict, idx: int) -> NewBar:
    """从原始 K 线 dict 创建 NewBar(对应 czsc 的 NewBar::new_from_raw)"""
    return NewBar(
        dt=kline["open_time"],
        open=float(kline["open"]),
        close=float(kline["close"]),
        high=float(kline["high"]),
        low=float(kline["low"]),
        vol=float(kline.get("volume", 0)),
        amount=float(kline.get("amount", 0)),
        elements=[idx],
    )


def remove_include(k1: NewBar, k2: NewBar, k3_raw: dict, k3_idx: int) -> tuple[bool, NewBar]:
    """
    去除包含关系 — 完全对齐 czsc remove_include 函数。

    Args:
        k1: 前一根去包含 K 线
        k2: 当前去包含 K 线
        k3_raw: 新到的原始 K 线 dict
        k3_idx: k3_raw 在原始 K 线列表中的索引

    Returns:
        (has_include, new_bar):
            has_include=True 表示 k2 与 k3 有包含关系,new_bar 是合并后的 K 线(替换 k2)
            has_include=False 表示无包含关系,new_bar 是从 k3 创建的新 K 线(追加)
    """
    # 1. 根据 k1.high 和 k2.high 确定方向
    if k1.high < k2.high:
        direction = "up"
    elif k1.high > k2.high:
        direction = "down"
    else:
        # k1.high == k2.high: czsc 返回 (false, k3 as new bar)
        return (False, _new_bar_from_raw(k3_raw, k3_idx))

    k3 = _new_bar_from_raw(k3_raw, k3_idx)

    # 2. 检查 k2 与 k3 是否存在包含关系
    has_inclusion = (
        (k2.high <= k3.high and k2.low >= k3.low)
        or (k2.high >= k3.high and k2.low <= k3.low)
    )

    if not has_inclusion:
        return (False, k3)

    # 3. 按方向合并 k2 和 k3
    if direction == "up":
        high = max(k2.high, k3.high)
        low = max(k2.low, k3.low)
        # dt 取较高 K 线的时间(对应 czsc: if k2.high > k3.high { k2.dt } else { k3.dt })
        dt = k2.dt if k2.high > k3.high else k3.dt
    else:  # direction == "down"
        high = min(k2.high, k3.high)
        low = min(k2.low, k3.low)
        # dt 取较低 K 线的时间(对应 czsc: if k2.low < k3.low { k2.dt } else { k3.dt })
        dt = k2.dt if k2.low < k3.low else k3.dt

    # open/close 对齐 czsc: k3.open > k3.close 时 (high, low),否则 (low, high)
    k3_open = float(k3_raw["open"])
    k3_close = float(k3_raw["close"])
    open_, close = (high, low) if k3_open > k3_close else (low, high)

    # elements: k2 中除 dt==k3.dt 之外的所有元素 + k3
    k3_dt = k3_raw["open_time"]
    merged_elements = [i for i in k2.elements if i != k3_idx] + [k3_idx]
    # czsc 限制 elements 最多 100 个,这里也限制
    if len(merged_elements) > 100:
        merged_elements = merged_elements[-100:]

    new_bar = NewBar(
        dt=dt,
        open=open_,
        close=close,
        high=high,
        low=low,
        vol=k2.vol + k3.vol,
        amount=k2.amount + k3.amount,
        elements=merged_elements,
    )
    return (True, new_bar)


def merge_containment(raw_klines: list[dict]) -> list[tuple[MergedKLine, int]]:
    """
    批量处理 K 线包含关系(对齐 czsc update_bar 中的去包含逻辑)。

    逐根调用 remove_include,维护 bars_ubi 列表。
    输出兼容旧接口:list[tuple[MergedKLine, direction]]
    direction: 1=up, -1=down, 0=未确定(仅首根或 high 相等时)

    Args:
        raw_klines: 原始 K 线列表,每根含 open_time/open/high/low/close/volume

    Returns:
        list[tuple[MergedKLine, int]]: 合并后的 K 线及方向
    """
    raw_count = len(raw_klines)
    if raw_count == 0:
        return []

    bars_ubi: list[NewBar] = []

    for i, kline in enumerate(raw_klines):
        if len(bars_ubi) < 2:
            bars_ubi.append(_new_bar_from_raw(kline, i))
        else:
            k1 = bars_ubi[-2]
            k2 = bars_ubi[-1]
            has_include, k3 = remove_include(k1, k2, kline, i)
            if has_include:
                # 替换最后一根
                bars_ubi[-1] = k3
            else:
                bars_ubi.append(k3)

    # 转换为兼容旧接口的 MergedKLine
    result: list[tuple[MergedKLine, int]] = []
    for i, bar in enumerate(bars_ubi):
        if i == 0:
            direction = 0
        elif bars_ubi[i - 1].high < bar.high:
            direction = 1
        elif bars_ubi[i - 1].high > bar.high:
            direction = -1
        else:
            direction = 0

        mk = MergedKLine(
            open_time=bar.dt,
            high=bar.high,
            low=bar.low,
            raw_indices=list(bar.elements),
            merged_count=len(bar.elements),
        )
        result.append((mk, direction))

    logger.info(f"merge_containment: {raw_count} raw -> {len(result)} merged (czsc algorithm)")
    return result


def get_bars_ubi(raw_klines: list[dict]) -> list[NewBar]:
    """
    获取去包含关系后的 NewBar 列表(供 check_fxs/check_bi 使用)。

    这是 czsc 算法的核心数据结构,check_fxs 在 bars_ubi 上扫描分型。
    """
    bars_ubi: list[NewBar] = []
    for i, kline in enumerate(raw_klines):
        if len(bars_ubi) < 2:
            bars_ubi.append(_new_bar_from_raw(kline, i))
        else:
            k1 = bars_ubi[-2]
            k2 = bars_ubi[-1]
            has_include, k3 = remove_include(k1, k2, kline, i)
            if has_include:
                bars_ubi[-1] = k3
            else:
                bars_ubi.append(k3)
    return bars_ubi
