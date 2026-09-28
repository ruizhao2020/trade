"""建议落成策略模板的路径（纯逻辑，不触碰数据库）。"""

from app.engine.advisor.registry import build_candidate_space
from app.engine.advisor.types import CandidateResult
from app.services.advisor_service import (
    AdvisorService,
    candidate_from_payload,
    candidate_payload,
)


def _service() -> AdvisorService:
    # to_template / payload 转换都是纯逻辑，不访问外部依赖
    return AdvisorService(None, None, None, None)


def _first(candidates, predicate):
    return next(item for item in candidates if predicate(item))


def test_indicator_candidate_becomes_a_primary_level_condition():
    candidates, _ = build_candidate_space()
    candidate = _first(
        candidates,
        lambda item: item.family == "均线" and item.entry.kind == "compare" and item.primary_level == "1d",
    )

    template = _service().to_template(CandidateResult(candidate=candidate))

    condition = template.condition_groups[0].conditions[0]
    assert template.primary_tf == "1d"
    # 入场在主周期时条件不写级别（走主周期）
    assert condition.timeframe_id is None
    assert condition.left.source == "price"
    assert condition.right.source == "indicator"
    assert condition.operator in {"gt", "lt", "crossAbove", "crossBelow", "rising", "falling"}
    # 出场参数来自候选
    assert template.trade_params is not None
    assert template.trade_params.stop_loss_type == candidate.exit.stop_loss_type


def test_chan_candidate_becomes_a_secondary_level_condition():
    candidates, _ = build_candidate_space()
    candidate = _first(candidates, lambda item: item.entry.kind == "chan_point")

    template = _service().to_template(CandidateResult(candidate=candidate))

    condition = template.condition_groups[0].conditions[0]
    # 缠论入场取次级别：模板声明次级周期，条件用「次级周期」哨兵值
    assert template.secondary_tfs == [candidate.secondary_level]
    assert condition.timeframe_id == "secondary"
    assert condition.left.source == "chan"
    assert condition.left.element == "buySellPoint"
    assert condition.left.property == candidate.entry.chan_point


def test_candidate_survives_a_payload_round_trip():
    candidates, _ = build_candidate_space()
    for candidate in (candidates[0], _first(candidates, lambda item: item.entry.kind == "chan_point")):
        restored = candidate_from_payload(candidate_payload(candidate))
        assert restored.id == candidate.id
        assert restored.primary_level == candidate.primary_level
        assert restored.entry_level == candidate.entry_level
        assert restored.secondary_level == candidate.secondary_level
        assert restored.entry == candidate.entry
        assert restored.exit == candidate.exit


def test_candidate_ids_are_stable_across_processes():
    """候选 id 不能用 hash()：它受 PYTHONHASHSEED 影响，会让结论无法重放。"""
    first, _ = build_candidate_space(budget=200)
    second, _ = build_candidate_space(budget=200)
    assert [item.id for item in first] == [item.id for item in second]
    assert len({item.id for item in first}) == len(first), "候选 id 不应重复"
