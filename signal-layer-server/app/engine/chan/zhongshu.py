"""
============================================================================
段 和 中枢 检测（缠论第四、五阶段）
============================================================================

## zhongshu.py 功能
1. build_duans: 从笔构建线段（段 = 连续同向笔的组合）
2. 定义 Duan 数据结构

## 段（Duan）构建规则
- 笔是段的基本组成单元
- 连续同向的笔合并为一段
- 段的方向由组成它的笔决定

## 中枢识别（在 signal.py 中）
- 至少 3 段的重叠区间构成中枢
- 中枢区间 = [max(各段低点), min(各段高点)]
"""

from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Literal
from app.engine.chan.bi import Bi

logger = logging.getLogger(__name__)


@dataclass
class Duan:
    index: int
    direction: Literal["up", "down"]
    bi_indices: list[int]
    start_time: int
    end_time: int
    start_price: float
    end_price: float
    high: float
    low: float
    feat_elements: list[dict] | None = None
    merged_feat: list[dict] | None = None
    fenxing_type: str | None = None


def build_duans(bis: list[Bi]) -> list[Duan]:
    """
    从笔构建段 — 严格对齐缠论原著"特征序列分型法"。

    ## 缠论原著算法(《教你炒股票》第 71、78 课)

    ### 段的基本定义
    - 至少 3 笔组成
    - 段方向 = 第一笔方向
    - 向上线段:起于底、终于顶(终点价格 > 起点价格)
    - 向下线段:起于顶、终于底(终点价格 < 起点价格)

    ### 特征序列定义(关键)
    - 向上线段的特征序列 = 段内所有**向下笔**(反向笔)
      每个特征元素 = (向下笔的起点价 = 顶, 向下笔的终点价 = 底)
      即 (start_price, end_price) of 向下笔
    - 向下线段的特征序列 = 段内所有**向上笔**(反向笔)
      每个特征元素 = (向上笔的起点价 = 底, 向上笔的终点价 = 顶)
      即 (start_price, end_price) of 向上笔
    注意:用笔的起止价,不是 high/low(max/min)。

    ### 包含合并(同 K 线去包含)
    - 相邻两元素若存在包含关系,按段方向相反的方向合并
    - 向上线段(向下笔序列):按"向下"方向合并 → 取 min(顶), min(底)
    - 向下线段(向上笔序列):按"向上"方向合并 → 取 max(底), max(顶)

    ### 分型确认段结束
    - 合并后的特征序列出现顶分型 → 向上线段结束
      顶分型:S1.顶 < S2.顶 > S3.顶 且 S1.底 < S2.底 > S3.底
    - 出现底分型 → 向下线段结束
      底分型:S1.顶 > S2.顶 < S3.顶 且 S1.底 > S2.底 < S3.底
    - 段终点 = S2 对应反向笔的起点(= 前一根同向笔的终点 = 段内极值点)

    ### 方向交替
    分型确认后,新段方向必然相反。
    """
    bi_count = len(bis)
    if bi_count < 3:
        logger.info(f"build_duans: {bi_count} bis (need >=3) -> 0 duans")
        return []

    duans: list[Duan] = []
    i = 0  # 当前段起始笔索引

    while i < bi_count - 2:
        seg_dir = bis[i].direction
        # 特征序列元素:(first_price, last_price, bi_index)
        # first/last 是反向笔的起点价/终点价(非 high/low)
        feat_elements: list[tuple[float, float, int]] = []

        end_idx = bi_count - 1  # 默认延伸到最后
        found_end = False
        # 候选分型位置和段内极值(用于回滚判断)
        candidate_end = -1  # 候选段末笔索引
        seg_extreme_price: float  # 段内极值(向下段=最低,向上段=最高)

        if seg_dir == "down":
            seg_extreme_price = bis[i].start_price  # 向下段起点是最高
        else:
            seg_extreme_price = bis[i].start_price  # 向上段起点是最低

        for j in range(i + 1, bi_count):
            b = bis[j]
            # 反向笔加入特征序列
            if b.direction != seg_dir:
                feat_elements.append((b.start_price, b.end_price, j))

            # 更新段内极值(向下段跟踪最低,向上段跟踪最高)
            if seg_dir == "down":
                seg_extreme_price = min(seg_extreme_price, b.end_price)
            else:
                seg_extreme_price = max(seg_extreme_price, b.end_price)

            # 如果已有候选分型,检查是否被后续笔破坏
            # 向下段:后续笔创新低(低于候选段末笔的终点)→ 候选分型作废,继续延伸
            # 向上段:后续笔创新高(高于候选段末笔的终点)→ 候选分型作废,继续延伸
            if found_end:
                last_candidate_end_price = bis[candidate_end].end_price
                broken = (
                    (seg_dir == "down" and b.end_price < last_candidate_end_price)
                    or (seg_dir == "up" and b.end_price > last_candidate_end_price)
                )
                if broken:
                    # 候选分型被破坏,撤销,继续延伸
                    found_end = False
                    candidate_end = -1
                    # 重置 end_idx 为延伸到最后(否则 end_idx 仍保留被破坏候选的值,
                    # 会导致段提前在已作废的候选位置终止)
                    end_idx = bi_count - 1

            # 至少 3 个元素(合并后)才能判断分型
            merged = _merge_feature_elements(feat_elements, seg_dir)
            if len(merged) < 3:
                continue

            # 检查最后 3 个元素是否形成分型(仅在没有有效候选时检测)
            if not found_end:
                is_top = _is_fx_top(merged[-3], merged[-2], merged[-1])
                is_bot = _is_fx_bottom(merged[-3], merged[-2], merged[-1])

                if seg_dir == "up" and is_top:
                    s2_bi_idx = merged[-2][2]
                    candidate_end = _find_seg_end_by_extreme(bis, i, s2_bi_idx - 1, seg_dir)
                    end_idx = candidate_end
                    found_end = True
                elif seg_dir == "down" and is_bot:
                    s2_bi_idx = merged[-2][2]
                    candidate_end = _find_seg_end_by_extreme(bis, i, s2_bi_idx - 1, seg_dir)
                    end_idx = candidate_end
                    found_end = True

        # 构建段 [i, end_idx]
        seg_bis = bis[i:end_idx + 1]
        if len(seg_bis) >= 3:
            if found_end:
                duan = _make_duan(len(duans), seg_dir, seg_bis)
                duan.feat_elements = [
                    {"first": f[0], "last": f[1], "bi": f[2]} for f in feat_elements
                ]
                duan.merged_feat = [
                    {"first": f[0], "last": f[1], "bi": f[2]} for f in merged
                ]
                duan.fenxing_type = "top" if seg_dir == "up" else "bottom"
                duans.append(duan)
            else:
                first = seg_bis[0]
                last = seg_bis[-1]
                direction_ok = (
                    (seg_dir == "up" and last.end_price > first.start_price)
                    or (seg_dir == "down" and last.end_price < first.start_price)
                )
                if direction_ok:
                    duan = _make_duan_simple(len(duans), seg_dir, seg_bis)
                    duan.feat_elements = [
                        {"first": f[0], "last": f[1], "bi": f[2]} for f in feat_elements
                    ]
                    duan.merged_feat = [
                        {"first": f[0], "last": f[1], "bi": f[2]} for f in merged
                    ]
                    duans.append(duan)
                else:
                    if duans:
                        prev = duans[-1]
                        prev.bi_indices.extend(b.index for b in seg_bis)
                        prev_seg_bis = [bis[k] for k in prev.bi_indices]
                        updated = _make_duan_simple(prev.index, prev.direction, prev_seg_bis)
                        prev.start_time = updated.start_time
                        prev.end_time = updated.end_time
                        prev.start_price = updated.start_price
                        prev.end_price = updated.end_price
                        prev.high = updated.high
                        prev.low = updated.low

        if found_end and end_idx + 1 < bi_count:
            i = end_idx + 1
        else:
            break

    logger.info(f"build_duans: {bi_count} bis -> {len(duans)} duans (特征序列分型法)")
    return duans


def _find_seg_end_by_extreme(
    bis: list[Bi], start_idx: int, end_idx_bound: int, seg_dir: str,
) -> int:
    """
    在 [start_idx, end_idx_bound] 范围内,找到段末笔的索引。
    段末笔 = 同向笔中极值最优的那根:
      - 向上线段:同向笔(向上笔)中 end_price 最大的
      - 向下线段:同向笔(向下笔)中 end_price 最小的
    返回该笔的索引。
    """
    best_idx = end_idx_bound
    if seg_dir == "up":
        best_price = -float("inf")
        for k in range(start_idx, end_idx_bound + 1):
            if bis[k].direction == seg_dir and bis[k].end_price > best_price:
                best_price = bis[k].end_price
                best_idx = k
    else:
        best_price = float("inf")
        for k in range(start_idx, end_idx_bound + 1):
            if bis[k].direction == seg_dir and bis[k].end_price < best_price:
                best_price = bis[k].end_price
                best_idx = k
    return best_idx


def _merge_feature_elements(
    elements: list[tuple[float, float, int]],
    seg_dir: str,
) -> list[tuple[float, float, int]]:
    """
    特征序列包含合并 — 对齐缠论 K 线去包含逻辑。

    elements: (first_price, last_price, bi_index)
      - 向上线段(向下笔):first=顶(start_price), last=底(end_price)
      - 向下线段(向上笔):first=底(start_price), last=顶(end_price)

    包含判断:两元素的 [min(first,last), max(first,last)] 区间有包含关系

    合并方向(与段方向相反):
      - 向上线段 → 按"向下"合并 → 取 min(first), min(last)
      - 向下线段 → 按"向上"合并 → 取 max(first), max(last)
    """
    if len(elements) < 2:
        return list(elements)

    def to_range(e: tuple[float, float, int]) -> tuple[float, float]:
        """元素的价格区间 [low, high]"""
        return (min(e[0], e[1]), max(e[0], e[1]))

    merged: list[tuple[float, float, int]] = [elements[0]]

    for curr in elements[1:]:
        prev = merged[-1]
        prev_lo, prev_hi = to_range(prev)
        curr_lo, curr_hi = to_range(curr)
        # 包含关系:一方完全包含另一方
        has_inclusion = (
            (prev_lo <= curr_lo and prev_hi >= curr_hi)
            or (prev_lo >= curr_lo and prev_hi <= curr_hi)
        )
        if not has_inclusion:
            merged.append(curr)
            continue

        # 有包含,按段方向相反的方向合并
        if seg_dir == "up":
            # 向上线段:特征序列是向下笔,按"向下"合并 → 取小
            new_first = min(prev[0], curr[0])
            new_last = min(prev[1], curr[1])
        else:
            # 向下线段:特征序列是向上笔,按"向上"合并 → 取大
            new_first = max(prev[0], curr[0])
            new_last = max(prev[1], curr[1])
        new_idx = max(prev[2], curr[2])
        merged[-1] = (new_first, new_last, new_idx)

    return merged


def _is_fx_top(s1, s2, s3) -> bool:
    """顶分型:S1.high < S2.high > S3.high 且 S1.low < S2.low > S3.low"""
    return s1[0] < s2[0] and s2[0] > s3[0] and s1[1] < s2[1] and s2[1] > s3[1]


def _is_fx_bottom(s1, s2, s3) -> bool:
    """底分型:S1.high > S2.high < S3.high 且 S1.low > S2.low < S3.low"""
    return s1[0] > s2[0] and s2[0] < s3[0] and s1[1] > s2[1] and s2[1] < s3[1]


def _make_duan(index: int, direction: str, seg_bis: list[Bi]) -> Duan:
    """
    从一组笔构造段(找到分型时使用,端点取段内极值)。
    段端点按段方向取段内极值笔的端点(确保方向约束满足):
      - 向上段:起点 = 最低点(某向下笔的终点 or 第一笔起点),终点 = 最高点(某向上笔的终点)
      - 向下段:起点 = 最高点(某向上笔的终点 or 第一笔起点),终点 = 最低点(某向下笔的终点)
    时间升序:起点时间 < 终点时间(极值笔按时间先后)
    相邻段端点对齐:前段终点 = 后段起点(都是同极值笔的端点)。
    """
    # 找段内极值对应的笔端点(price, time)
    all_endpoints: list[tuple[float, int]] = []
    for b in seg_bis:
        all_endpoints.append((b.start_price, b.start_time))
        all_endpoints.append((b.end_price, b.end_time))

    high_price = max(p for p, _ in all_endpoints)
    low_price = min(p for p, _ in all_endpoints)
    all_endpoints.sort(key=lambda x: x[1])

    if direction == "up":
        low_pt = min((pt for pt in all_endpoints if pt[0] == low_price), key=lambda x: x[1])
        high_pt = max((pt for pt in all_endpoints if pt[0] == high_price), key=lambda x: x[1])
        start_price, start_time = low_pt
        end_price, end_time = high_pt
    else:
        high_pt = min((pt for pt in all_endpoints if pt[0] == high_price), key=lambda x: x[1])
        low_pt = max((pt for pt in all_endpoints if pt[0] == low_price), key=lambda x: x[1])
        start_price, start_time = high_pt
        end_price, end_time = low_pt

    if start_time > end_time:
        first = seg_bis[0]
        last = seg_bis[-1]
        start_price, start_time = first.start_price, first.start_time
        end_price, end_time = last.end_price, last.end_time

    return Duan(
        index=index,
        direction=direction,
        bi_indices=[b.index for b in seg_bis],
        start_time=start_time,
        end_time=end_time,
        start_price=start_price,
        end_price=end_price,
        high=high_price,
        low=low_price,
    )


def _make_duan_simple(index: int, direction: str, seg_bis: list[Bi]) -> Duan:
    """
    从一组笔构造段(未找到分型、段延伸到最后时使用)。
    段端点 = 第一笔起点 + 末同向笔终点。
      - 向上段:终点 = 最后一个向上笔的终点(段内最高点附近)
      - 向下段:终点 = 最后一个向下笔的终点(段内最低点附近)
    由于笔方向严格交替,末同向笔 = seg_bis[-1](若同向)或 seg_bis[-2](若反向)。
    起止时间天然升序(笔连续),相邻段端点对齐。
    """
    first = seg_bis[0]
    high = max(b.high for b in seg_bis)
    low = min(b.low for b in seg_bis)

    # 段终点 = 末同向笔的终点(与段方向相同的最后一笔)
    if seg_bis[-1].direction == direction:
        end_bi = seg_bis[-1]
    else:
        # 最后一笔与段反向,取倒数第二笔(必然同向)
        end_bi = seg_bis[-2] if len(seg_bis) >= 2 else seg_bis[-1]

    return Duan(
        index=index,
        direction=direction,
        bi_indices=[b.index for b in seg_bis],
        start_time=first.start_time,
        end_time=end_bi.end_time,
        start_price=first.start_price,
        end_price=end_bi.end_price,
        high=high,
        low=low,
    )
