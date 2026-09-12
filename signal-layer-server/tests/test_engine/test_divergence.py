from __future__ import annotations

from app.engine.chan.bi import Bi
from app.engine.chan.divergence import identify_divergences
from app.engine.chan.signal import Zhongshu, identify_buy_sell_points


def make_bi(
    index: int,
    direction: str,
    start_price: float,
    end_price: float,
    *,
    high: float | None = None,
    low: float | None = None,
) -> Bi:
    return Bi(
        index=index,
        direction=direction,
        fx_a=None,
        fx_b=None,
        bars=[],
        high=max(start_price, end_price) if high is None else high,
        low=min(start_price, end_price) if low is None else low,
        start_time=index * 10,
        end_time=index * 10 + 9,
        start_price=start_price,
        end_price=end_price,
        power=abs(end_price - start_price),
    )


def make_zhongshu(direction: str) -> Zhongshu:
    return Zhongshu(
        index=0,
        high=110,
        low=90,
        mid=100,
        start_time=0,
        end_time=39,
        level="bi",
        bi_indices=[0, 1, 2, 3],
        broken=True,
        break_direction=direction,
    )


def test_bottom_divergence_creates_first_buy_point() -> None:
    bis = [
        make_bi(0, "up", 90, 110),
        make_bi(1, "down", 110, 90),
        make_bi(2, "up", 90, 94),
        make_bi(3, "down", 94, 83),
        make_bi(4, "up", 83, 89),
    ]
    # 中枢内向下笔(index=1)力度 20；离开笔(index=3)力度 11 且创新低。
    divergences = identify_divergences(bis, [make_zhongshu("down")])

    assert len(divergences) == 1
    divergence = divergences[0]
    assert divergence.type == "bottom"
    assert divergence.reference_bi_index == 1
    assert divergence.current_bi_index == 3
    assert divergence.strength_ratio == 0.55
    assert len(divergence.reasons) == 3
    assert "新低" in divergence.reasons[0]

    points = identify_buy_sell_points(bis, [make_zhongshu("down")], divergences)
    first_buy = next(point for point in points if point.type == "buy1")
    assert first_buy.reason == "bottom_divergence"
    assert first_buy.divergence_index == divergence.index
    assert first_buy.price == 83


def test_top_divergence_creates_first_sell_point() -> None:
    bis = [
        make_bi(0, "down", 110, 90),
        make_bi(1, "up", 90, 110),
        make_bi(2, "down", 110, 106),
        make_bi(3, "up", 106, 117),
        make_bi(4, "down", 117, 111),
    ]
    divergences = identify_divergences(bis, [make_zhongshu("up")])

    assert len(divergences) == 1
    divergence = divergences[0]
    assert divergence.type == "top"
    assert divergence.reference_bi_index == 1
    assert divergence.current_bi_index == 3
    assert "新高" in divergence.reasons[0]

    points = identify_buy_sell_points(bis, [make_zhongshu("up")], divergences)
    first_sell = next(point for point in points if point.type == "sell1")
    assert first_sell.reason == "top_divergence"
    assert first_sell.divergence_index == divergence.index
    assert first_sell.price == 117


def test_new_extreme_without_power_decay_is_not_divergence_or_first_point() -> None:
    bis = [
        make_bi(0, "up", 90, 110),
        make_bi(1, "down", 110, 96),
        make_bi(2, "up", 96, 108),
        make_bi(3, "down", 108, 83),
        make_bi(4, "up", 83, 89),
    ]
    zhongshu = make_zhongshu("down")
    divergences = identify_divergences(bis, [zhongshu])

    assert divergences == []
    assert all(
        point.type != "buy1"
        for point in identify_buy_sell_points(bis, [zhongshu], divergences)
    )
