"""
============================================================================
中枢与买卖点 — 基于 czsc ZS 数据结构 + 标准 3 笔重叠扩展法
============================================================================

## czsc 的 ZS 数据结构 (crates/czsc-core/src/objects/zs.rs)

czsc 的 analyze 模块只定义了 ZS 数据结构和 is_valid 校验,
没有提供中枢识别函数(get_zs)。识别算法需要自行实现。

### ZS 字段(对齐 czsc)
- bis: 构成中枢的笔列表
- sdt: 中枢开始时间(第一笔起点)
- edt: 中枢结束时间(最后一笔终点)
- sdir: 中枢第一笔方向
- edir: 中枢最后一笔方向
- zg: 中枢上沿 = min(前3笔 high)
- zd: 中枢下沿 = max(前3笔 low)
- zz: 中枢中轴 = (zg + zd) / 2
- gg: 中枢最高点 = max(所有笔 high)
- dd: 中枢最低点 = min(所有笔 low)

### ZS::is_valid 校验
- zg >= zd(有重叠区间)
- 所有笔与中枢区间[zd, zg]相交:
  - 笔 high 在区间内,或
  - 笔 low 在区间内,或
  - 笔完全包含区间

## 中枢识别算法(标准 3 笔重叠扩展法)

1. 从 BI 列表第 0 笔开始,取连续 3 笔
2. zg = min(3 笔 high), zd = max(3 笔 low)
3. 若 zg > zd,构成中枢
4. 向后扩展: 后续笔与 [zd, zg] 相交则纳入中枢,更新 gg/dd
5. 某笔不相交 → 中枢终止
6. 从终止后下一笔开始找下一个中枢

## 买卖点(标准缠论定义)
- 一买: 下跌趋势末端,向下突破中枢后的低点
- 二买: 一买后回调不破一买低点
- 三买: 中枢向上突破后回踩不进中枢
- 一卖/二卖/三卖: 对称定义
"""

from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Literal
from app.engine.chan.bi import Bi

logger = logging.getLogger(__name__)


@dataclass
class Zhongshu:
    """
    中枢数据结构(对齐 czsc ZS)。

    zg/zd: 中枢上/下沿(前 3 笔重叠区间)
    zz: 中枢中轴
    gg/dd: 中枢最高/最低点(所有笔极值)
    """
    index: int
    high: float         # 兼容旧接口,等于 zg
    low: float          # 兼容旧接口,等于 zd
    mid: float          # 兼容旧接口,等于 zz
    start_time: int     # 对应 czsc sdt
    end_time: int       # 对应 czsc edt
    level: str          # "bi"(基于笔)或"duan"(基于段)
    bi_indices: list[int]  # 构成中枢的笔索引
    broken: bool        # 是否已突破
    break_direction: Literal["up", "down"] | None = None  # 突破方向


@dataclass
class BuySellPoint:
    """买卖点数据结构"""
    type: Literal["buy1", "buy2", "buy3", "sell1", "sell2", "sell3"]
    price: float
    time: int
    zhongshu_index: int | None
    bi_index: int
    confirmed: bool
    strength: float


def identify_zhongshus_from_bis(bis: list[Bi]) -> list[Zhongshu]:
    """
    从笔序列构建中枢 — 标准 3 笔重叠扩展法。

    算法对齐 czsc ZS::new 的字段定义:
    - zg = min(前 3 笔 high)
    - zd = max(前 3 笔 low)
    - gg = max(所有笔 high)
    - dd = min(所有笔 low)
    - zz = (zg + zd) / 2

    扩展规则: 后续笔与 [zd, zg] 相交则纳入中枢
    突破判断: 某笔不相交 → 中枢终止,记录突破方向

    Args:
        bis: 笔列表

    Returns:
        list[Zhongshu]: 中枢列表
    """
    bi_count = len(bis)
    if bi_count < 3:
        logger.info(f"identify_zhongshus_from_bis: {bi_count} bis (need >=3) -> 0 zhongshus")
        return []

    zhongshus: list[Zhongshu] = []
    i = 0

    while i + 2 < bi_count:
        b1 = bis[i]
        b2 = bis[i + 1]
        b3 = bis[i + 2]

        # 前 3 笔重叠区间(对齐 czsc ZS::new)
        zg = min(b1.high, b2.high, b3.high)
        zd = max(b1.low, b2.low, b3.low)

        if zg > zd:
            # 有效中枢,开始扩展
            zs_bi_indices = [b1.index, b2.index, b3.index]
            gg = max(b1.high, b2.high, b3.high)
            dd = min(b1.low, b2.low, b3.low)
            end_bi_idx = i + 2

            # 向后扩展
            for j in range(i + 3, bi_count):
                bj = bis[j]
                # 笔与中枢区间相交则纳入
                if bj.low <= zg and bj.high >= zd:
                    zs_bi_indices.append(bj.index)
                    gg = max(gg, bj.high)
                    dd = min(dd, bj.low)
                    end_bi_idx = j
                else:
                    # 不相交,中枢终止
                    break

            # 判断突破方向
            break_bi_idx = end_bi_idx + 1
            broken = break_bi_idx < bi_count
            break_dir: Literal["up", "down"] | None = None
            if broken:
                break_bi = bis[break_bi_idx]
                if break_bi.low > zg:
                    break_dir = "up"
                elif break_bi.high < zd:
                    break_dir = "down"

            zz = (zg + zd) / 2

            zhongshus.append(Zhongshu(
                index=len(zhongshus),
                high=zg,
                low=zd,
                mid=zz,
                start_time=b1.start_time,
                end_time=bis[end_bi_idx].end_time,
                level="bi",
                bi_indices=zs_bi_indices,
                broken=broken,
                break_direction=break_dir,
            ))

            i = end_bi_idx + 1
        else:
            i += 1

    logger.info(f"identify_zhongshus_from_bis: {bi_count} bis -> {len(zhongshus)} zhongshus (czsc ZS algorithm)")
    return zhongshus


def identify_zhongshus(duans: list[Duan]) -> list[Zhongshu]:
    """
    兼容旧接口: 从段构建中枢。
    新代码请使用 identify_zhongshus_from_bis(基于笔,对齐 czsc)。
    """
    duan_count = len(duans)
    if duan_count < 3:
        logger.info(f"identify_zhongshus (legacy): {duan_count} duans -> 0 zhongshus")
        return []

    zhongshus: list[Zhongshu] = []
    i = 0

    while i + 2 < duan_count:
        d1 = duans[i]
        d2 = duans[i + 1]
        d3 = duans[i + 2]

        zg = min(d1.high, d2.high, d3.high)
        zd = max(d1.low, d2.low, d3.low)

        if zg > zd:
            zs_duans = [d1.index, d2.index, d3.index]
            end_idx = i + 2

            for j in range(i + 3, duan_count):
                dj = duans[j]
                if dj.low <= zg and dj.high >= zd:
                    zs_duans.append(dj.index)
                    end_idx = j
                else:
                    break

            broken = end_idx + 1 < duan_count
            break_dir = None
            if broken:
                break_duan = duans[end_idx + 1]
                break_dir = "up" if break_duan.high > zg else "down"

            zhongshus.append(Zhongshu(
                index=len(zhongshus),
                high=zg,
                low=zd,
                mid=(zg + zd) / 2,
                start_time=d1.start_time,
                end_time=duans[end_idx].end_time,
                level="duan",
                bi_indices=zs_duans,
                broken=broken,
                break_direction=break_dir,
            ))
            i = end_idx + 1
        else:
            i += 1

    logger.info(f"identify_zhongshus (legacy): {duan_count} duans -> {len(zhongshus)} zhongshus")
    return zhongshus


def identify_buy_sell_points(
    bis: list[Bi],
    zhongshus: list[Zhongshu],
) -> list[BuySellPoint]:
    """
    识别缠论买卖点 — 标准定义。

    买点(向下突破中枢后):
    - 一买: 突破笔的终点(低点)
    - 二买: 一买后反弹再下跌,不破一买低点
    - 三买: 中枢向上突破后回踩不进中枢

    卖点(向上突破中枢后):
    - 一卖: 突破笔的终点(高点)
    - 二卖: 一卖后回调再反弹,不破一卖高点
    - 三卖: 中枢向下突破后反弹不进中枢
    """
    points: list[BuySellPoint] = []
    bi_count = len(bis)

    if not bis or not zhongshus:
        return points

    bi_index_map = {b.index: idx for idx, b in enumerate(bis)}

    for zs in zhongshus:
        if not zs.broken or not zs.break_direction:
            continue

        # 找突破笔(中枢最后一笔的下一笔)
        last_bi_idx_in_zs = zs.bi_indices[-1] if zs.bi_indices else -1
        break_bi_idx = bi_index_map.get(last_bi_idx_in_zs + 1)
        if break_bi_idx is None or break_bi_idx >= bi_count:
            continue
        break_bi = bis[break_bi_idx]

        if zs.break_direction == "down":
            # 向下突破 → 买点
            # 一买: 突破笔低点
            points.append(BuySellPoint(
                type="buy1", price=break_bi.low, time=break_bi.end_time,
                zhongshu_index=zs.index, bi_index=break_bi.index,
                confirmed=True, strength=zs.low - break_bi.low,
            ))

            # 二买: 反弹后下跌不破一买低点
            if break_bi_idx + 2 < bi_count:
                rebound = bis[break_bi_idx + 1]
                drop = bis[break_bi_idx + 2]
                if (rebound.direction == "up" and drop.direction == "down"
                        and drop.low > break_bi.low):
                    points.append(BuySellPoint(
                        type="buy2", price=drop.low, time=drop.end_time,
                        zhongshu_index=zs.index, bi_index=drop.index,
                        confirmed=True, strength=drop.low - break_bi.low,
                    ))

            # 三买: 反弹超中枢上沿后回踩不进中枢
            if break_bi_idx + 2 < bi_count:
                rebound = bis[break_bi_idx + 1]
                drop = bis[break_bi_idx + 2]
                if (rebound.direction == "up" and rebound.high > zs.high
                        and drop.direction == "down" and drop.low > zs.high):
                    points.append(BuySellPoint(
                        type="buy3", price=drop.low, time=drop.end_time,
                        zhongshu_index=zs.index, bi_index=drop.index,
                        confirmed=True, strength=drop.low - zs.high,
                    ))

        elif zs.break_direction == "up":
            # 向上突破 → 卖点
            # 一卖: 突破笔高点
            points.append(BuySellPoint(
                type="sell1", price=break_bi.high, time=break_bi.end_time,
                zhongshu_index=zs.index, bi_index=break_bi.index,
                confirmed=True, strength=break_bi.high - zs.high,
            ))

            # 二卖: 回调后反弹不破一卖高点
            if break_bi_idx + 2 < bi_count:
                pullback = bis[break_bi_idx + 1]
                rebound = bis[break_bi_idx + 2]
                if (pullback.direction == "down" and rebound.direction == "up"
                        and rebound.high < break_bi.high):
                    points.append(BuySellPoint(
                        type="sell2", price=rebound.high, time=rebound.end_time,
                        zhongshu_index=zs.index, bi_index=rebound.index,
                        confirmed=True, strength=break_bi.high - rebound.high,
                    ))

    # 三卖: 向下突破中枢后反弹不进中枢
    for zs in zhongshus:
        if not zs.broken or zs.break_direction != "down":
            continue
        last_bi_idx_in_zs = zs.bi_indices[-1] if zs.bi_indices else -1
        break_bi_idx = bi_index_map.get(last_bi_idx_in_zs + 1)
        if break_bi_idx is None or break_bi_idx + 1 >= bi_count:
            continue
        rebound = bis[break_bi_idx + 1] if break_bi_idx + 1 < bi_count else None
        if rebound and rebound.direction == "up" and rebound.high < zs.low:
            points.append(BuySellPoint(
                type="sell3", price=rebound.high, time=rebound.end_time,
                zhongshu_index=zs.index, bi_index=rebound.index,
                confirmed=True, strength=zs.low - rebound.high,
            ))

    points.sort(key=lambda p: p.time)

    type_counts: dict[str, int] = {}
    for p in points:
        type_counts[p.type] = type_counts.get(p.type, 0) + 1
    logger.info(f"identify_buy_sell_points: {bi_count} bis, {len(zhongshus)} zhongshus -> {len(points)} points {type_counts}")
    return points
