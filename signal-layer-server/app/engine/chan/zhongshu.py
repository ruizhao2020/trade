"""
============================================================================
段 和 中枢 检测（缠论第四、五阶段）
============================================================================

## zhongshu.py 功能
1. build_duans: 从笔构建线段（段 = 连续同向笔的组合）
2. 定义 Duan 数据结构

## 段（Duan）构建规则
- 先用特征序列分型法划分基础线段（至少 3 笔）
- 再把未破坏趋势起点、幅度较小的回抽合并进趋势段
- 段的方向由构成它的笔决定，相邻段共享端点

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


@dataclass
class _BaseDuan:
    """基础线段（特征序列分型法结果），用于后续走势回抽合并。"""

    start: int
    end: int
    direction: str
    fenxing: str | None
    feats: list[tuple[float, float, int]]
    merged: list[tuple[float, float, int]]
    absorbed_pullback: bool = False


def build_duans(bis: list[Bi]) -> list[Duan]:
    """
    从笔构建段 — 特征序列基础线段 + 走势回抽合并。

    ## 第一阶段：特征序列分型法（缠论原著第 67、71 课）
    1. 段方向 = 起始笔方向，段至少 3 笔。
    2. 特征序列 = 与段方向相反的笔；向上段取向下笔 (顶, 底)，
       向下段取向上笔 (底, 顶)。
    3. 特征序列按包含关系合并（向上段取小、向下段取大）。
    4. 向上段出现顶分型 / 向下段出现底分型 → 段结束。
    5. 段终点 = 分型中间反向笔之前、段内同向笔的极值笔（可能早于分型确认位置，
       其后的笔归入下一段）。

    ## 第二阶段：走势回抽合并
    基础线段中的反向线段若同时满足以下条件，说明它只是趋势中的回抽，而不是反转：
    - 没有跌破/升破前一同向线段的起点；
    - 回抽幅度小于前一同向线段的幅度；
    - 其后同向线段仍然有效（终点超越起点）。
    合并后的段终点取后一同向线段的终点（回抽之后趋势的最后一个极值），
    这样一条走势段会跨过中间的回抽，而不是被回抽切成多条线段。

    无效线段（终点未超越起点）并入前一段，视为趋势延续；
    若首笔单独成段（不足 3 笔），直接跳过：它只是行情开篇的一笔，
    不能把后续线段拉回到更早的端点。
    """
    bi_count = len(bis)
    if bi_count < 3:
        logger.info(f"build_duans: {bi_count} bis (need >=3) -> 0 duans")
        return []

    segments = _build_base_duans(bis)
    segments = _cleanup_base_duans(bis, segments)
    segments = _merge_pullback_segments(bis, segments)

    duans = [_make_duan(index, segment, bis) for index, segment in enumerate(segments)]
    logger.info(f"build_duans: {bi_count} bis -> {len(duans)} duans (特征序列+走势回抽合并)")
    return duans


def _build_base_duans(bis: list[Bi]) -> list[_BaseDuan]:
    """逐段扫描特征序列，得到基础线段。"""
    segments: list[_BaseDuan] = []
    start = 0
    while start + 2 < len(bis):
        segment = _scan_base_segment(bis, start)
        segments.append(segment)
        if segment.fenxing is None or segment.end + 1 <= start:
            break
        start = segment.end + 1
    return segments


def _scan_base_segment(bis: list[Bi], start: int) -> _BaseDuan:
    """扫描 [start, ...]，找到特征序列分型并返回基础线段。

    找不到分型时返回延伸到最后的一笔（未完成段）。
    """
    direction = bis[start].direction
    feats: list[tuple[float, float, int]] = []
    merged: list[tuple[float, float, int]] = []

    for j in range(start + 1, len(bis)):
        current = bis[j]
        if current.direction != direction:
            feats.append((current.start_price, current.end_price, j))
        merged = _merge_feature_elements(feats, direction)
        if len(merged) < 3:
            continue
        s1, s2, s3 = merged[-3], merged[-2], merged[-1]
        if direction == "up" and _is_fx_top(s1, s2, s3):
            bound = max(start, s2[2] - 1)
            end = _seg_extreme_bi(bis, start, bound, direction)
            return _BaseDuan(start, end, direction, "top", feats, merged)
        if direction == "down" and _is_fx_bottom(s1, s2, s3):
            bound = max(start, s2[2] - 1)
            end = _seg_extreme_bi(bis, start, bound, direction)
            return _BaseDuan(start, end, direction, "bottom", feats, merged)

    return _BaseDuan(start, len(bis) - 1, direction, None, feats, merged)


def _seg_extreme_bi(bis: list[Bi], start: int, end_bound: int, direction: str) -> int:
    """段内同向笔的极值笔索引（向上取最高 end_price，向下取最低 end_price）。

    极值相同取时间靠后的一笔，使段终点落在极值最后一次出现的位置。
    """
    best: int | None = None
    for k in range(start, min(end_bound, len(bis) - 1) + 1):
        if bis[k].direction != direction:
            continue
        if best is None:
            best = k
            continue
        price = bis[k].end_price
        best_price = bis[best].end_price
        if (direction == "up" and price >= best_price) or (direction == "down" and price <= best_price):
            best = k
    return best if best is not None else start


def _cleanup_base_duans(bis: list[Bi], segments: list[_BaseDuan]) -> list[_BaseDuan]:
    """剔除/吸收不足 3 笔或方向无效的基础线段。

    短段或方向无效段若夹在两条同向线段之间，说明它只是趋势中的一笔回抽，
    与前后两段合并；否则并入前一段。首段无法成段时直接跳过，
    不把后一段的起点拉到首笔起点（否则向上段会从一段下跌的开头开始）。
    """
    cleaned: list[_BaseDuan] = []
    position = 0

    while position < len(segments):
        segment = segments[position]
        length = segment.end - segment.start + 1
        if length < 3 or not _is_valid_segment(bis, segment):
            following = segments[position + 1] if position + 1 < len(segments) else None
            if cleaned and following is not None and cleaned[-1].direction == following.direction:
                previous = cleaned[-1]
                previous.end = following.end
                previous.fenxing = following.fenxing
                previous.feats = previous.feats + following.feats
                previous.merged = following.merged
                position += 2
                continue
            if cleaned:
                previous = cleaned[-1]
                if segment.end > previous.end:
                    previous.end = segment.end
                    previous.fenxing = None
                    previous.feats = []
                    previous.merged = []
            position += 1
            continue

        cleaned.append(segment)
        position += 1

    return cleaned


def _merge_pullback_segments(bis: list[Bi], segments: list[_BaseDuan]) -> list[_BaseDuan]:
    """把符合回抽条件的基础线段合并为走势段。"""
    changed = True
    while changed:
        changed = False
        for position in range(len(segments) - 2):
            trend = segments[position]
            pullback = segments[position + 1]
            following = segments[position + 2]

            if trend.absorbed_pullback or pullback.absorbed_pullback or following.absorbed_pullback:
                continue
            if trend.direction != following.direction:
                continue
            if not _is_valid_segment(bis, following):
                continue
            if _breaks_origin(bis, trend, pullback):
                continue
            # 回抽幅度必须小于趋势幅度的一半，否则更像是一段真实的来回走势。
            if _segment_amplitude(bis, pullback) * 2 >= _segment_amplitude(bis, trend):
                continue

            segments[position:position + 3] = [_BaseDuan(
                start=trend.start,
                end=following.end,
                direction=trend.direction,
                fenxing=following.fenxing,
                feats=trend.feats + following.feats,
                merged=following.merged,
                absorbed_pullback=True,
            )]
            changed = True
            break

    return segments


def _is_valid_segment(bis: list[Bi], segment: _BaseDuan) -> bool:
    """段的终点是否沿段方向超越起点。"""
    start_price = bis[segment.start].start_price
    end_price = bis[segment.end].end_price
    if segment.direction == "up":
        return end_price > start_price
    return end_price < start_price


def _segment_extremes(bis: list[Bi], segment: _BaseDuan) -> tuple[float, float]:
    """返回段的 (最高价, 最低价)。"""
    prices: list[float] = []
    for item in bis[segment.start:segment.end + 1]:
        prices.append(item.start_price)
        prices.append(item.end_price)
    return max(prices), min(prices)


def _breaks_origin(bis: list[Bi], trend: _BaseDuan, pullback: _BaseDuan) -> bool:
    """回抽是否跌破（向上段）或升破（向下段）趋势段的起点。"""
    origin = bis[trend.start].start_price
    high, low = _segment_extremes(bis, pullback)
    if trend.direction == "up":
        return low < origin
    return high > origin


def _segment_amplitude(bis: list[Bi], segment: _BaseDuan) -> float:
    """段的净幅度（终点相对起点的涨跌幅绝对值）。"""
    start_price = bis[segment.start].start_price
    end_price = bis[segment.end].end_price
    base = abs(start_price) if start_price else 1.0
    return abs(end_price - start_price) / base


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


def _make_duan(index: int, segment: _BaseDuan, bis: list[Bi]) -> Duan:
    """把最终走势段映射为 Duan。

    段端点取首笔起点 / 末笔终点，保证相邻段共享同一个端点；
    high/low 仍是整段的价格区间（可能包含段内回抽的极值）。
    """
    seg_bis = bis[segment.start:segment.end + 1]
    high, low = _segment_extremes(bis, segment)
    # 特征序列只保留本段范围内的元素：扫描时为了确认分型会越过段末，
    # 那些笔属于后续段，不能画在本段上。
    allowed = set(range(segment.start, segment.end + 1))
    feats = [item for item in segment.feats if item[2] in allowed]
    merged = [item for item in segment.merged if item[2] in allowed]
    return Duan(
        index=index,
        direction=segment.direction,
        bi_indices=[item.index for item in seg_bis],
        start_time=seg_bis[0].start_time,
        end_time=seg_bis[-1].end_time,
        start_price=seg_bis[0].start_price,
        end_price=seg_bis[-1].end_price,
        high=high,
        low=low,
        feat_elements=[
            {"first": item[0], "last": item[1], "bi": item[2]}
            for item in feats
        ] or None,
        merged_feat=[
            {"first": item[0], "last": item[1], "bi": item[2]}
            for item in merged
        ] or None,
        fenxing_type=segment.fenxing,
    )
