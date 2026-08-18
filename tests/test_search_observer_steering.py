from app.search_observer_llm import DirectionRecommendation, ObserverAction
from app.search_observer_promotion import (
    ActionFamily,
    FamilyPromotionEvidence,
    PromotionDecision,
    PromotionState,
)
from app.search_observer_steering import (
    SteeringState,
    validate_bounded_continuation_steering,
)


def _family(family: ActionFamily, state: PromotionState) -> FamilyPromotionEvidence:
    eligible = state == PromotionState.ELIGIBLE_FOR_BOUNDED_STEERING
    return FamilyPromotionEvidence(
        family=family,
        outcome_count=8 if eligible else 0,
        decided_count=8 if eligible else 0,
        supported_count=7 if eligible else 0,
        contradicted_count=1 if eligible else 0,
        inconclusive_count=0,
        supported_ratio=0.875 if eligible else 0.0,
        contradicted_ratio=0.125 if eligible else 0.0,
        high_confidence_decided_count=4 if eligible else 0,
        high_confidence_contradicted_ratio=0.0,
        lower_confidence_decided_count=4 if eligible else 0,
        lower_confidence_contradicted_ratio=0.25 if eligible else 0.0,
        state=state,
        reason_codes=["family_gate_satisfied"] if eligible else ["insufficient_family_samples"],
    )


def _promotion(*, continuation_eligible: bool = True) -> PromotionDecision:
    continuation_state = (
        PromotionState.ELIGIBLE_FOR_BOUNDED_STEERING
        if continuation_eligible
        else PromotionState.SHADOW_ONLY
    )
    return PromotionDecision(
        state=(
            PromotionState.ELIGIBLE_FOR_BOUNDED_STEERING
            if continuation_eligible
            else PromotionState.SHADOW_ONLY
        ),
        total_outcomes=30,
        total_scorable=30,
        heterogeneous_batch_count=4,
        recent_batch_supported_ratios=[0.75, 0.80],
        quality_evidence_complete=True,
        quality_guard_passed=True,
        routing_changed_count=0,
        families=[
            _family(ActionFamily.CONTINUATION, continuation_state),
            _family(ActionFamily.ADJUSTMENT, PromotionState.SHADOW_ONLY),
            _family(ActionFamily.STOP, PromotionState.SHADOW_ONLY),
            _family(ActionFamily.ESCALATE, PromotionState.SHADOW_ONLY),
        ],
        reason_codes=["global_gate_satisfied"] if continuation_eligible else ["shadow_only"],
    )


def _rec(index: int, action: ObserverAction) -> DirectionRecommendation:
    return DirectionRecommendation(
        direction_index=index,
        action=action,
        confidence=0.8,
        rationale="bounded test recommendation",
        refined_queries=[],
    )


def test_runtime_gate_off_is_routing_equivalent_noop():
    result = validate_bounded_continuation_steering(
        [_rec(0, ObserverAction.CONTINUE)],
        enabled=False,
        promotion=_promotion(),
        remaining_query_budget=2,
        effective_regime="balanced",
        direction_count=3,
    )

    assert result.state == SteeringState.DISABLED
    assert result.routing_changed is False
    assert result.accepted_direction_indexes == []
    assert result.max_second_wave_queries == 0
    assert result.reason_codes == ["runtime_gate_disabled"]


def test_only_continuation_family_can_be_admitted_and_budget_caps_it():
    result = validate_bounded_continuation_steering(
        [
            _rec(0, ObserverAction.REFINE),
            _rec(1, ObserverAction.CONTINUE),
            _rec(2, ObserverAction.BOOST),
            _rec(3, ObserverAction.STOP),
        ],
        enabled=True,
        promotion=_promotion(),
        remaining_query_budget=1,
        effective_regime="discovery",
        direction_count=4,
    )

    assert result.state == SteeringState.ACCEPTED
    assert result.routing_changed is False
    assert result.accepted_direction_indexes == [1]
    assert result.accepted_actions == [ObserverAction.CONTINUE]
    assert result.max_second_wave_queries == 1
    assert result.rejected_action_count == 1


def test_promotion_gate_is_fail_closed():
    result = validate_bounded_continuation_steering(
        [_rec(0, ObserverAction.CONTINUE)],
        enabled=True,
        promotion=_promotion(continuation_eligible=False),
        remaining_query_budget=2,
        effective_regime="precision",
        direction_count=1,
    )

    assert result.state == SteeringState.REJECTED
    assert result.routing_changed is False
    assert result.reason_codes == ["continuation_promotion_gate_not_satisfied"]


def test_adjustment_stop_and_escalate_remain_shadow_only():
    result = validate_bounded_continuation_steering(
        [
            _rec(0, ObserverAction.REFINE),
            _rec(1, ObserverAction.SLOW),
            _rec(2, ObserverAction.STOP),
            _rec(3, ObserverAction.ESCALATE),
        ],
        enabled=True,
        promotion=_promotion(),
        remaining_query_budget=4,
        effective_regime="balanced",
        direction_count=4,
    )

    assert result.state == SteeringState.REJECTED
    assert result.routing_changed is False
    assert result.accepted_direction_indexes == []
    assert result.rejected_action_count == 4
    assert result.reason_codes == ["no_eligible_continuation_recommendations"]


def test_invalid_regime_and_zero_budget_reject_before_scheduler():
    invalid_regime = validate_bounded_continuation_steering(
        [_rec(0, ObserverAction.CONTINUE)],
        enabled=True,
        promotion=_promotion(),
        remaining_query_budget=1,
        effective_regime="auto",
        direction_count=1,
    )
    no_budget = validate_bounded_continuation_steering(
        [_rec(0, ObserverAction.CONTINUE)],
        enabled=True,
        promotion=_promotion(),
        remaining_query_budget=0,
        effective_regime="balanced",
        direction_count=1,
    )

    assert invalid_regime.state == SteeringState.REJECTED
    assert invalid_regime.reason_codes == ["invalid_effective_search_regime"]
    assert no_budget.state == SteeringState.REJECTED
    assert no_budget.reason_codes == ["no_remaining_query_budget"]
