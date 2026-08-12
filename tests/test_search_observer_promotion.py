from app.search_observer_llm import ObserverAction
from app.search_observer_promotion import (
    ActionFamily,
    PromotionState,
    PromotionThresholds,
    QualityGuard,
    evaluate_promotion_gate,
)
from app.search_observer_scoring import (
    ObservedMarginalYield,
    RecommendationOutcome,
    RecommendationVerdict,
)


def outcome(action, verdict, confidence=0.8, *, routing_changed=False):
    score = 0.4 if verdict == RecommendationVerdict.SUPPORTED else -0.4
    if verdict == RecommendationVerdict.INCONCLUSIVE:
        score = 0.0
    return RecommendationOutcome(
        mission_id="m",
        attempt_id="a",
        direction_index=0,
        action=action,
        confidence=confidence,
        outcome=ObservedMarginalYield(
            added_queries=1,
            added_raw_results=10,
            added_unique_domains=5,
            added_qualified_candidates=5,
            added_direct_or_official_candidates=2,
            duplicate_results=1,
            excluded_results=1,
            latency_ms=100,
            cost_rub=0.01,
        ),
        verdict=verdict,
        score=score,
        reason_code="test",
        routing_changed=routing_changed,
    )


def family(decision, target):
    return next(item for item in decision.families if item.family == target)


def test_current_two_outcome_evidence_stays_shadow_only():
    decision = evaluate_promotion_gate(
        [
            outcome(ObserverAction.REFINE, RecommendationVerdict.CONTRADICTED, 0.7),
            outcome(ObserverAction.SLOW, RecommendationVerdict.SUPPORTED, 0.8),
        ],
        heterogeneous_batch_count=1,
    )
    assert decision.state == PromotionState.SHADOW_ONLY
    assert "insufficient_total_samples" in decision.reason_codes
    assert "insufficient_heterogeneous_batches" in decision.reason_codes


def test_family_can_become_eligible_only_after_thresholds():
    samples = [
        outcome(ObserverAction.CONTINUE, RecommendationVerdict.SUPPORTED, 0.8)
        for _ in range(28)
    ] + [
        outcome(ObserverAction.CONTINUE, RecommendationVerdict.CONTRADICTED, 0.6)
        for _ in range(2)
    ]
    decision = evaluate_promotion_gate(samples, heterogeneous_batch_count=3)
    assert decision.state == PromotionState.ELIGIBLE_FOR_BOUNDED_STEERING
    continuation = family(decision, ActionFamily.CONTINUATION)
    assert continuation.state == PromotionState.ELIGIBLE_FOR_BOUNDED_STEERING
    assert continuation.supported_ratio == 0.933333
    assert continuation.contradicted_ratio == 0.066667


def test_high_confidence_calibration_regression_blocks_family():
    samples = [
        outcome(ObserverAction.SLOW, RecommendationVerdict.CONTRADICTED, 0.9),
        outcome(ObserverAction.SLOW, RecommendationVerdict.CONTRADICTED, 0.9),
        outcome(ObserverAction.SLOW, RecommendationVerdict.SUPPORTED, 0.9),
        outcome(ObserverAction.SLOW, RecommendationVerdict.SUPPORTED, 0.6),
        outcome(ObserverAction.SLOW, RecommendationVerdict.SUPPORTED, 0.6),
    ]
    decision = evaluate_promotion_gate(
        samples,
        heterogeneous_batch_count=2,
        thresholds=PromotionThresholds(min_total_scorable=5, min_supported_ratio=0.5, max_contradicted_ratio=0.5),
    )
    adjustment = family(decision, ActionFamily.ADJUSTMENT)
    assert adjustment.state == PromotionState.SHADOW_ONLY
    assert "high_confidence_calibration_regression" in adjustment.reason_codes


def test_quality_regression_blocks_everything():
    samples = [
        outcome(ObserverAction.CONTINUE, RecommendationVerdict.SUPPORTED)
        for _ in range(30)
    ]
    decision = evaluate_promotion_gate(
        samples,
        heterogeneous_batch_count=3,
        quality_guard=QualityGuard(qualified_yield_regressed=True),
    )
    assert decision.state == PromotionState.SHADOW_ONLY
    assert decision.quality_guard_passed is False
    assert "quality_regression_guard_failed" in decision.reason_codes


def test_routing_change_fails_global_gate():
    samples = [
        outcome(ObserverAction.CONTINUE, RecommendationVerdict.SUPPORTED)
        for _ in range(29)
    ] + [
        outcome(ObserverAction.CONTINUE, RecommendationVerdict.SUPPORTED, routing_changed=True)
    ]
    decision = evaluate_promotion_gate(samples, heterogeneous_batch_count=3)
    assert decision.state == PromotionState.SHADOW_ONLY
    assert decision.routing_changed_count == 1
    assert "shadow_routing_changed" in decision.reason_codes


def test_escalate_never_becomes_automatic_steering_family():
    samples = [
        outcome(ObserverAction.ESCALATE, RecommendationVerdict.NOT_SCORABLE)
        for _ in range(30)
    ]
    decision = evaluate_promotion_gate(samples, heterogeneous_batch_count=3)
    escalate = family(decision, ActionFamily.ESCALATE)
    assert escalate.state == PromotionState.SHADOW_ONLY
    assert "economic_gate_required" in escalate.reason_codes
