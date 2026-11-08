"""走势完全分类的判定口径。"""

from app.engine.chan.classification import classify_next_moves
from app.engine.chan.divergence import Divergence
from app.engine.chan.signal import Zhongshu


def zhongshu(high=110.0, low=100.0) -> Zhongshu:
    return Zhongshu(
        index=0, high=high, low=low, mid=(high + low) / 2,
        start_time=0, end_time=10, level="bi", bi_indices=[0, 1, 2],
        broken=False, break_direction=None,
    )


def divergence(kind: str) -> Divergence:
    return Divergence(
        index=0, type=kind, level="bi", kind="consolidation",
        price=100.0, time=10, zhongshu_index=0,
        reference_bi_index=0, current_bi_index=2,
        reference_power=1.0, current_power=0.5, strength_ratio=0.5,
        confirmed=True, reasons=[],
    )


def test_above_zhongshu_favors_three_buy_continuation():
    result = classify_next_moves(115.0, [zhongshu()], "up", [])

    assert result.position == "above"
    active = {item.key for item in result.scenarios if item.active}
    assert "continue_up" in active
    assert "reverse_down" not in active


def test_inside_zhongshu_favors_range():
    result = classify_next_moves(105.0, [zhongshu()], "down", [])

    assert result.position == "inside"
    active = {item.key for item in result.scenarios if item.active}
    assert "range" in active


def test_below_zhongshu_favors_three_sell_reversal():
    result = classify_next_moves(95.0, [zhongshu()], "down", [])

    assert result.position == "below"
    active = {item.key for item in result.scenarios if item.active}
    assert "reverse_down" in active


def test_confirmed_top_divergence_marks_reversal_scenario():
    result = classify_next_moves(115.0, [zhongshu()], "up", [divergence("top")])

    active = {item.key for item in result.scenarios if item.active}
    assert "divergence_reverse" in active


def test_no_zhongshu_returns_unknown():
    result = classify_next_moves(100.0, [], "up", [])

    assert result.position == "unknown"
    assert result.scenarios == []


def test_scenarios_cover_four_complete_branches():
    result = classify_next_moves(105.0, [zhongshu()], "up", [])

    assert [item.key for item in result.scenarios] == [
        "continue_up", "range", "reverse_down", "divergence_reverse",
    ]
    for item in result.scenarios:
        assert item.condition and item.implication
