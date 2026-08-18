from __future__ import annotations

from dataclasses import dataclass

from app.search_observer_promotion import (
    ActionFamily,
    FamilyPromotionEvidence,
    PromotionDecision,
    PromotionState,
)


@dataclass(frozen=True)
class VerifiedPromotionSnapshot:
    evidence_id: str
    evidence_sample_count: int
    decision: PromotionDecision


def verified_continuation_promotion_snapshot() -> VerifiedPromotionSnapshot:
    """Return the reviewed N=30 promotion snapshot shipped with this release.

    This is deliberately code-versioned instead of recomputed from mutable runtime
    traces. Updating the snapshot requires a normal reviewed code change with fresh
    evidence. Only the continuation family is eligible; all other families remain
    shadow-only.
    """
    continuation = FamilyPromotionEvidence(
        family=ActionFamily.CONTINUATION,
        outcome_count=8,
        decided_count=8,
        supported_count=7,
        contradicted_count=1,
        inconclusive_count=0,
        supported_ratio=0.875,
        contradicted_ratio=0.125,
        high_confidence_decided_count=4,
        high_confidence_contradicted_ratio=0.0,
        lower_confidence_decided_count=4,
        lower_confidence_contradicted_ratio=0.25,
        state=PromotionState.ELIGIBLE_FOR_BOUNDED_STEERING,
        reason_codes=["family_gate_satisfied"],
    )

    def shadow_family(family: ActionFamily, reason: str) -> FamilyPromotionEvidence:
        return FamilyPromotionEvidence(
            family=family,
            outcome_count=0,
            decided_count=0,
            supported_count=0,
            contradicted_count=0,
            inconclusive_count=0,
            supported_ratio=0.0,
            contradicted_ratio=0.0,
            high_confidence_decided_count=0,
            high_confidence_contradicted_ratio=0.0,
            lower_confidence_decided_count=0,
            lower_confidence_contradicted_ratio=0.0,
            state=PromotionState.SHADOW_ONLY,
            reason_codes=[reason],
        )

    decision = PromotionDecision(
        state=PromotionState.ELIGIBLE_FOR_BOUNDED_STEERING,
        total_outcomes=30,
        total_scorable=30,
        heterogeneous_batch_count=4,
        recent_batch_supported_ratios=[0.75, 0.875],
        quality_evidence_complete=True,
        quality_guard_passed=True,
        routing_changed_count=0,
        families=[
            continuation,
            shadow_family(ActionFamily.ADJUSTMENT, "calibration_insufficient_for_steering"),
            shadow_family(ActionFamily.STOP, "insufficient_family_samples"),
            shadow_family(ActionFamily.ESCALATE, "economic_gate_required"),
        ],
        reason_codes=["reviewed_n30_continuation_snapshot"],
    )
    return VerifiedPromotionSnapshot(
        evidence_id="search-observer-n30-2026-08-13",
        evidence_sample_count=30,
        decision=decision,
    )
