"""缠论背驰识别：比较中枢离开笔与中枢内最近同向笔的价格极值和力度。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.engine.chan.bi import Bi


@dataclass
class Divergence:
    index: int
    type: Literal["top", "bottom"]
    level: Literal["bi"]
    kind: Literal["consolidation"]
    price: float
    time: int
    zhongshu_index: int
    reference_bi_index: int
    current_bi_index: int
    reference_power: float
    current_power: float
    strength_ratio: float
    confirmed: bool
    reasons: list[str]


def identify_divergences(bis: list[Bi], zhongshus: list) -> list[Divergence]:
    """识别中枢离开笔的顶/底背驰。

    顶背驰：向上离开笔创新高，同时价差力度小于中枢内最近向上笔。
    底背驰：向下离开笔创新低，同时价差力度小于中枢内最近向下笔。
    """
    if not bis or not zhongshus:
        return []
    position_by_index = {item.index: position for position, item in enumerate(bis)}
    divergences: list[Divergence] = []

    for zhongshu in zhongshus:
        if not zhongshu.broken or zhongshu.break_direction not in ("up", "down"):
            continue
        last_index = zhongshu.bi_indices[-1] if zhongshu.bi_indices else None
        if last_index is None:
            continue
        # 中枢最后一笔是从中枢区间离开的笔；下一笔完全位于中枢外，
        # 由中枢识别逻辑用来确认突破。笔方向严格交替，因此不能把
        # 下一笔误当成离开笔，否则真实笔序列不会满足方向条件。
        current_position = position_by_index.get(last_index)
        if current_position is None:
            continue
        current = bis[current_position]
        expected_direction = "up" if zhongshu.break_direction == "up" else "down"
        if current.direction != expected_direction:
            continue

        references = [
            bis[position_by_index[index]]
            for index in zhongshu.bi_indices
            if (
                index != current.index
                and index in position_by_index
                and bis[position_by_index[index]].direction == expected_direction
            )
        ]
        if not references:
            continue
        reference = references[-1]
        reference_power = abs(reference.power or (reference.end_price - reference.start_price))
        current_power = abs(current.power or (current.end_price - current.start_price))
        if reference_power <= 0 or current_power >= reference_power:
            continue

        if expected_direction == "up":
            if current.high <= reference.high:
                continue
            divergence_type: Literal["top", "bottom"] = "top"
            price = current.high
            extreme_reason = "离开笔向上突破中枢并创出新高"
        else:
            if current.low >= reference.low:
                continue
            divergence_type = "bottom"
            price = current.low
            extreme_reason = "离开笔向下突破中枢并创出新低"

        divergences.append(Divergence(
            index=len(divergences),
            type=divergence_type,
            level="bi",
            kind="consolidation",
            price=price,
            time=current.end_time,
            zhongshu_index=zhongshu.index,
            reference_bi_index=reference.index,
            current_bi_index=current.index,
            reference_power=reference_power,
            current_power=current_power,
            strength_ratio=round(current_power / reference_power, 4),
            confirmed=True,
            reasons=[
                extreme_reason,
                "离开笔力度小于中枢内最近同向笔",
                "后一笔位于中枢外，背驰已经确认",
            ],
        ))

    return divergences
