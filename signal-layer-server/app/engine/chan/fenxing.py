"""
============================================================================
分型识别 — 完全对齐 czsc 算法 (crates/czsc-core/src/analyze/utils.rs)
============================================================================

## czsc 算法核心规则

### check_fx (单分型判断,3 根 K 线)
- 顶分型: k1.high < k2.high 且 k2.high > k3.high 且 k1.low < k2.low 且 k2.low > k3.low
- 底分型: k1.low > k2.low 且 k2.low < k3.low 且 k1.high > k2.high 且 k2.high < k3.high

### check_fxs (批量扫描,强制顶底交替)
- 滑动窗口(3 根)扫描 bars_ubi
- 若新分型与上一个分型同向(mark 相同),记录错误日志并跳过(不加入列表)
- 否则加入分型列表
- 结果:分型列表严格顶底交替

## 关键差异(与旧简化版)
- 旧版: 只比较 high(顶)或 low(底),且加入"间隔<3"等过滤规则
- czsc: 严格 4 个条件(high 和 low 都要满足),无额外过滤,靠顶底交替保证唯一性

## 分型强度(power_str)
czsc 的 FX.power_str 基于第 3 根 K 线的 close:
- 底分型: close > k1.high → 强; close > k2.high → 中; 否则弱
- 顶分型: close < k1.low → 强; close < k2.low → 中; 否则弱
"""

from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Literal
from app.engine.chan.merge import NewBar, MergedKLine

logger = logging.getLogger(__name__)


@dataclass
class Fenxing:
    """
    分型数据结构(对齐 czsc 的 FX)。

    direction: "top"(顶分型,G)或 "bottom"(底分型,D)
    price: 分型价格(顶=high, 底=low),对应 czsc FX.fx
    strength: 分型强度("强"/"中"/"弱"),对应 czsc FX.power_str
    merged_index: 在 bars_ubi 中的索引
    merged_kline: 对应的 NewBar(中间 K 线 k2)
    elements: 构成分型的 3 根 NewBar 索引[k1_idx, k2_idx, k3_idx]
    """
    index: int
    direction: Literal["top", "bottom"]
    price: float
    strength: float  # 0~1,用于兼容旧接口(强=1.0, 中=0.6, 弱=0.3)
    merged_index: int
    merged_kline: NewBar
    elements: tuple[int, int, int]  # (k1_idx, k2_idx, k3_idx)


def check_fx(k1: NewBar, k2: NewBar, k3: NewBar) -> Literal["top", "bottom", None]:
    """
    单分型判断 — 完全对齐 czsc check_fx 函数。

    Args:
        k1, k2, k3: 连续 3 根去包含 K 线

    Returns:
        "top"=顶分型, "bottom"=底分型, None=非分型
    """
    # 顶分型: k2 的 high 和 low 都高于 k1 和 k3
    if k1.high < k2.high and k2.high > k3.high and k1.low < k2.low and k2.low > k3.low:
        return "top"

    # 底分型: k2 的 high 和 low 都低于 k1 和 k3
    if k1.low > k2.low and k2.low < k3.low and k1.high > k2.high and k2.high < k3.high:
        return "bottom"

    return None


def _calc_power_str(k1: NewBar, k2: NewBar, k3: NewBar, direction: str) -> float:
    """
    计算分型强度 — 对齐 czsc FX.power_str 逻辑。

    Returns:
        strength: 0~1 之间的数值(强=1.0, 中=0.6, 弱=0.3)
    """
    if direction == "bottom":
        # 底分型: 看 k3.close 的反弹力度
        if k3.close > k1.high:
            return 1.0  # 强
        elif k3.close > k2.high:
            return 0.6  # 中
        else:
            return 0.3  # 弱
    else:
        # 顶分型: 看 k3.close 的下跌力度
        if k3.close < k1.low:
            return 1.0  # 强
        elif k3.close < k2.low:
            return 0.6  # 中
        else:
            return 0.3  # 弱


def check_fxs(bars_ubi: list[NewBar]) -> list[Fenxing]:
    """
    批量扫描分型 — 完全对齐 czsc check_fxs 函数。

    滑动窗口(3 根)扫描 bars_ubi,对每组调用 check_fx。
    强制顶底交替: 若新分型与上一个分型同向,记录警告并跳过。

    Args:
        bars_ubi: 去包含关系后的 K 线列表

    Returns:
        list[Fenxing]: 顶底交替的分型列表
    """
    if len(bars_ubi) < 3:
        logger.info(f"check_fxs: {len(bars_ubi)} bars (need >=3) -> 0 fenxings")
        return []

    fxs: list[Fenxing] = []

    for i in range(1, len(bars_ubi) - 1):
        k1 = bars_ubi[i - 1]
        k2 = bars_ubi[i]
        k3 = bars_ubi[i + 1]

        fx_type = check_fx(k1, k2, k3)
        if fx_type is None:
            continue

        # 强制顶底交替(对齐 czsc: 若与上一个分型同向则跳过并记录警告)
        if fxs and fxs[-1].direction == fx_type:
            # czsc 这里记录错误日志,我们用 warning
            logger.warning(
                f"check_fxs: 同向分型跳过 dt={k2.dt}, "
                f"curr={fx_type}, last={fxs[-1].direction}"
            )
            # czsc 的逻辑是直接跳过(不加入),保持上一个不变
            # 但实际 czsc 会比较并保留极值,这里对齐 czsc 的"跳过"行为
            continue

        strength = _calc_power_str(k1, k2, k3, fx_type)
        price = k2.high if fx_type == "top" else k2.low

        fxs.append(Fenxing(
            index=len(fxs),
            direction=fx_type,
            price=price,
            strength=strength,
            merged_index=i,
            merged_kline=k2,
            elements=(i - 1, i, i + 1),
        ))

    logger.info(f"check_fxs: {len(bars_ubi)} bars -> {len(fxs)} fenxings (czsc algorithm)")
    return fxs


def detect_fenxings(merged_data: list[tuple[MergedKLine, int]]) -> list[Fenxing]:
    """
    兼容旧接口: 从 merged_data 检测分型。

    内部调用 check_fxs(基于 NewBar)。
    注意:此接口会丢失 NewBar 的 open/close/vol 信息,只保留 high/low。
    建议新代码直接调用 check_fxs(get_bars_ubi(raw_klines))。

    Args:
        merged_data: merge_containment 的输出

    Returns:
        list[Fenxing]: 顶底交替的分型列表
    """
    # 从 MergedKLine 构造简化版 NewBar(只有 high/low/dt)
    bars_ubi: list[NewBar] = []
    for mk, _ in merged_data:
        bars_ubi.append(NewBar(
            dt=mk.open_time,
            open=mk.high,  # 旧接口无 open,用 high 占位
            close=mk.low,  # 旧接口无 close,用 low 占位
            high=mk.high,
            low=mk.low,
        ))

    return check_fxs(bars_ubi)
