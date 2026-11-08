"""走势的完全分类：当前走势结束之后，后续结构只有有限几种可能。

缠论的「完全分类」不是预测方向，而是把「接下来可能发生什么」穷举出来，
每一种都带明确的触发条件。判定基准是最后一个笔中枢与当前价的关系。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.engine.chan.signal import Zhongshu
from app.engine.chan.divergence import Divergence


@dataclass
class NextScenario:
    key: str            # continue_up / range / reverse_down / divergence
    label: str
    condition: str      # 触发条件
    implication: str    # 触发后的后续结构
    active: bool        # 当前是否已经满足前提
    children: list["NextScenario"] = field(default_factory=list)  # 再往后一层的分类


@dataclass
class Classification:
    position: str       # above / inside / below / unknown
    zhongshu_high: float | None
    zhongshu_low: float | None
    last_close: float | None
    scenarios: list[NextScenario]


def classify_next_moves(
    last_close: float | None,
    zhongshus: list[Zhongshu],
    last_bi_direction: str | None,
    divergences: list[Divergence],
) -> Classification:
    """按最后一个笔中枢与当前价的关系，给出后续走势的完全分类。"""
    if not zhongshus or last_close is None:
        return Classification(
            position="unknown", zhongshu_high=None, zhongshu_low=None,
            last_close=last_close, scenarios=[],
        )

    zhongshu = zhongshus[-1]
    if last_close > zhongshu.high:
        position = "above"
    elif last_close < zhongshu.low:
        position = "below"
    else:
        position = "inside"

    confirmed_top = any(item.type == "top" and item.confirmed for item in divergences)
    confirmed_bottom = any(item.type == "bottom" and item.confirmed for item in divergences)
    last_divergence = divergences[-1] if divergences else None

    def child(key: str, label: str, condition: str, implication: str) -> NextScenario:
        return NextScenario(key=key, label=label, condition=condition, implication=implication, active=False)

    scenarios = [
        NextScenario(
            key="continue_up",
            label="向上延续（三买方向）",
            condition=f"回踩不跌破中枢上沿 {zhongshu.high:.2f}，随后再次向上",
            implication="形成三买，中枢上移，走出一段新的向上趋势",
            active=position == "above" and not confirmed_top,
            children=[
                child("three_buy_new_zone", "三买后新中枢上移",
                      "回踩确认不破中枢上沿后再次放量向上",
                      "形成新的向上中枢，趋势级别提升"),
                child("pullback_into_zone", "回踩回到中枢内",
                      "向上未站稳就跌回中枢区间",
                      "三买不成立，转为中枢扩展"),
                child("top_divergence_end", "向上段出现顶背驰",
                      "新的向上段力度小于前一段并确认",
                      "向上趋势结束，转入向下走势"),
            ],
        ),
        NextScenario(
            key="range",
            label="中枢扩展（盘整）",
            condition=f"价格回到中枢区间 {zhongshu.low:.2f} ~ {zhongshu.high:.2f} 内上下震荡",
            implication="走势延续盘整，中枢继续扩展，等待新的离开段",
            active=position == "inside",
            children=[
                child("break_up", "向上离开中枢",
                      f"放量突破中枢上沿 {zhongshu.high:.2f} 并站稳",
                      "走出向上离开段，进入三买观察"),
                child("break_down", "向下离开中枢",
                      f"跌破中枢下沿 {zhongshu.low:.2f} 并站稳",
                      "走出向下离开段，进入三卖观察"),
                child("keep_range", "继续盘整",
                      "价格始终在中枢区间内反复",
                      "中枢继续扩展，等待方向选择"),
            ],
        ),
        NextScenario(
            key="reverse_down",
            label="向下转折（三卖方向）",
            condition=f"跌破中枢下沿 {zhongshu.low:.2f}，反弹不再进入中枢",
            implication="形成三卖，中枢下移，走出一段新的向下趋势",
            active=position == "below",
            children=[
                child("three_sell_new_zone", "三卖后新中枢下移",
                      "反弹确认不进入中枢后再次向下",
                      "形成新的向下中枢，趋势级别提升"),
                child("rebound_into_zone", "反弹回到中枢内",
                      "向下未站稳就反弹回中枢区间",
                      "三卖不成立，转回中枢扩展"),
                child("bottom_divergence_end", "向下段出现底背驰",
                      "新的向下段力度小于前一段并确认",
                      "向下趋势结束，转入向上走势"),
            ],
        ),
        NextScenario(
            key="divergence_reverse",
            label="背驰转折",
            condition="离开段出现背驰（力度小于前一同向段）并确认",
            implication="原方向动能衰竭，至少引发一次次级别回抽",
            active=(confirmed_top if last_bi_direction == "up" else confirmed_bottom)
            if last_bi_direction else False,
        ),
    ]

    if last_divergence is not None and last_divergence.confirmed:
        for item in scenarios:
            if item.key == "divergence_reverse":
                item.active = True

    return Classification(
        position=position,
        zhongshu_high=zhongshu.high,
        zhongshu_low=zhongshu.low,
        last_close=last_close,
        scenarios=scenarios,
    )
