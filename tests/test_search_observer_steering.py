from app.search_observer_llm import DirectionRecommendation, ObserverAction
from app.search_observer_steering import (
    SteeringState,
    validate_bounded_continuation_steering,
)
from app.search_observer_verified_promotion import (
    ContinuationPromotionPermit,
    verified_continuation_promotion_permit,
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
        permit=verified_continuation_promotion_permit(),
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
        permit=verified_continuation_promotion_permit(),
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
    assert result.promotion_evidence_id == "search-observer-n30-2026-08-13"


def test_promotion_gate_is_fail_closed_on_insufficient_or_disabled_permit():
    insufficient = ContinuationPromotionPermit(
        evidence_id="insufficient",
        total_scorable=30,
        continuation_decided=4,
        continuation_supported=4,
        continuation_contradicted=0,
        heterogeneous_batch_count=4,
        eligible_for_bounded_steering=True,
    )
    disabled = verified_continuation_promotion_permit().model_copy(
        update={"eligible_for_bounded_steering": False}
    )

    for permit in (None, insufficient, disabled):
        result = validate_bounded_continuation_steering(
            [_rec(0, ObserverAction.CONTINUE)],
            enabled=True,
            permit=permit,
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
        permit=verified_continuation_promotion_permit(),
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
    permit = verified_continuation_promotion_permit()
    invalid_regime = validate_bounded_continuation_steering(
        [_rec(0, ObserverAction.CONTINUE)],
        enabled=True,
        permit=permit,
        remaining_query_budget=1,
        effective_regime="auto",
        direction_count=1,
    )
    no_budget = validate_bounded_continuation_steering(
        [_rec(0, ObserverAction.CONTINUE)],
        enabled=True,
        permit=permit,
        remaining_query_budget=0,
        effective_regime="balanced",
        direction_count=1,
    )

    assert invalid_regime.state == SteeringState.REJECTED
    assert invalid_regime.reason_codes == ["invalid_effective_search_regime"]
    assert no_budget.state == SteeringState.REJECTED
    assert no_budget.reason_codes == ["no_remaining_query_budget"]
