from __future__ import annotations

from collections import defaultdict
from enum import StrEnum
from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field

from app.search_observer_llm import ObserverAction
from app.search_observer_scoring import RecommendationOutcome, RecommendationVerdict


class PromotionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PromotionState(StrEnum):
    SHADOW_ONLY = "shadow_only"
    ELIGIBLE_FOR_BOUNDED_STEERING = "eligible_for_bounded_steering"


class ActionFamily(StrEnum):
    CONTINUATION = "continue_boost"
    ADJUSTMENT = "slow_refine"
    STOP = "stop"
    ESCALATE = "escalate"


class PromotionThresholds(PromotionModel):
    min_total_scorable: int = Field(default=30, ge=1)
    min_family_decided: int = Field(default=5, ge=1)
    min_supported_ratio: float = Field(default=0.70, ge=0.0, le=1.0)
    max_contradicted_ratio: float = Field(default=0.15, ge=0.0, le=1.0)
    min_heterogeneous_batches: int = Field(default=2, ge=1)
    high_confidence_floor: float = Field(default=0.75, ge=0.0, le=1.0)
    min_recent_batch_supported_ratio: float = Field(default=0.60, ge=0.0, le=1.0)
    consecutive_weak_batch_limit: int = Field(default=2, ge=2)


class QualityGuard(PromotionModel):
    qualified_yield_regressed: bool = False
    direct_or_official_yield_regressed: bool = False
    duplicate_or_excluded_waste_regressed: bool = False
    latency_or_cost_outside_policy: bool = False

    @property
    def passed(self) -> bool:
        return not any(
            (
                self.qualified_yield_regressed,
                self.direct_or_official_yield_regressed,
                self.duplicate_or_excluded_waste_regressed,
                self.latency_or_cost_outside_policy,
            )
        )


class FamilyPromotionEvidence(PromotionModel):
    family: ActionFamily
    outcome_count: int = Field(ge=0)
    decided_count: int = Field(ge=0)
    supported_count: int = Field(ge=0)
    contradicted_count: int = Field(ge=0)
    inconclusive_count: int = Field(ge=0)
    supported_ratio: float = Field(ge=0.0, le=1.0)
    contradicted_ratio: float = Field(ge=0.0, le=1.0)
    high_confidence_decided_count: int = Field(ge=0)
    high_confidence_contradicted_ratio: float = Field(ge=0.0, le=1.0)
    lower_confidence_decided_count: int = Field(ge=0)
    lower_confidence_contradicted_ratio: float = Field(ge=0.0, le=1.0)
    state: PromotionState
    reason_codes: list[str]


class PromotionDecision(PromotionModel):
    state: PromotionState
    total_outcomes: int = Field(ge=0)
    total_scorable: int = Field(ge=0)
    heterogeneous_batch_count: int = Field(ge=0)
    recent_batch_supported_ratios: list[float]
    quality_guard_passed: bool
    routing_changed_count: int = Field(ge=0)
    families: list[FamilyPromotionEvidence]
    reason_codes: list[str]


def action_family(action: ObserverAction) -> ActionFamily:
    if action in {ObserverAction.CONTINUE, ObserverAction.BOOST}:
        return ActionFamily.CONTINUATION
    if action in {ObserverAction.SLOW, ObserverAction.REFINE}:
        return ActionFamily.ADJUSTMENT
    if action == ObserverAction.STOP:
        return ActionFamily.STOP
    return ActionFamily.ESCALATE


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _family_evidence(
    family: ActionFamily,
    outcomes: list[RecommendationOutcome],
    thresholds: PromotionThresholds,
    quality_guard: QualityGuard,
) -> FamilyPromotionEvidence:
    decided = [
        item
        for item in outcomes
        if item.verdict in {RecommendationVerdict.SUPPORTED, RecommendationVerdict.CONTRADICTED}
    ]
    supported = sum(item.verdict == RecommendationVerdict.SUPPORTED for item in decided)
    contradicted = sum(item.verdict == RecommendationVerdict.CONTRADICTED for item in decided)
    inconclusive = sum(item.verdict == RecommendationVerdict.INCONCLUSIVE for item in outcomes)
    high = [item for item in decided if item.confidence >= thresholds.high_confidence_floor]
    low = [item for item in decided if item.confidence < thresholds.high_confidence_floor]
    high_contradicted = sum(item.verdict == RecommendationVerdict.CONTRADICTED for item in high)
    low_contradicted = sum(item.verdict == RecommendationVerdict.CONTRADICTED for item in low)
    supported_ratio = _ratio(supported, len(decided))
    contradicted_ratio = _ratio(contradicted, len(decided))
    high_rate = _ratio(high_contradicted, len(high))
    low_rate = _ratio(low_contradicted, len(low))

    reasons: list[str] = []
    if family == ActionFamily.ESCALATE:
        reasons.append("economic_gate_required")
    if len(decided) < thresholds.min_family_decided:
        reasons.append("insufficient_family_samples")
    if supported_ratio < thresholds.min_supported_ratio:
        reasons.append("supported_ratio_below_threshold")
    if contradicted_ratio > thresholds.max_contradicted_ratio:
        reasons.append("contradicted_ratio_above_threshold")
    if high and low and high_rate > low_rate:
        reasons.append("high_confidence_calibration_regression")
    if not quality_guard.passed:
        reasons.append("quality_regression_guard_failed")

    eligible = not reasons and family != ActionFamily.ESCALATE
    return FamilyPromotionEvidence(
        family=family,
        outcome_count=len(outcomes),
        decided_count=len(decided),
        supported_count=supported,
        contradicted_count=contradicted,
        inconclusive_count=inconclusive,
        supported_ratio=supported_ratio,
        contradicted_ratio=contradicted_ratio,
        high_confidence_decided_count=len(high),
        high_confidence_contradicted_ratio=high_rate,
        lower_confidence_decided_count=len(low),
        lower_confidence_contradicted_ratio=low_rate,
        state=(
            PromotionState.ELIGIBLE_FOR_BOUNDED_STEERING
            if eligible
            else PromotionState.SHADOW_ONLY
        ),
        reason_codes=reasons or ["family_gate_satisfied"],
    )


def _has_consecutive_weak_batches(
    recent_batch_supported_ratios: list[float],
    thresholds: PromotionThresholds,
) -> bool:
    window = thresholds.consecutive_weak_batch_limit
    if len(recent_batch_supported_ratios) < window:
        return False
    return all(
        ratio < thresholds.min_recent_batch_supported_ratio
        for ratio in recent_batch_supported_ratios[-window:]
    )


def evaluate_promotion_gate(
    outcomes: Iterable[RecommendationOutcome],
    *,
    heterogeneous_batch_count: int,
    recent_batch_supported_ratios: Iterable[float] = (),
    quality_guard: QualityGuard | None = None,
    thresholds: PromotionThresholds | None = None,
) -> PromotionDecision:
    """Evaluate promotion eligibility only; never changes routing or calls providers."""
    items = list(outcomes)
    guard = quality_guard or QualityGuard()
    limits = thresholds or PromotionThresholds()
    recent_ratios = [round(float(item), 6) for item in recent_batch_supported_ratios]
    if any(item < 0.0 or item > 1.0 for item in recent_ratios):
        raise ValueError("recent_batch_supported_ratio_out_of_range")
    scorable = [item for item in items if item.verdict != RecommendationVerdict.NOT_SCORABLE]
    routing_changed_count = sum(item.routing_changed for item in items)

    grouped: dict[ActionFamily, list[RecommendationOutcome]] = defaultdict(list)
    for item in items:
        grouped[action_family(item.action)].append(item)

    families = [
        _family_evidence(family, grouped.get(family, []), limits, guard)
        for family in ActionFamily
    ]

    reasons: list[str] = []
    if len(scorable) < limits.min_total_scorable:
        reasons.append("insufficient_total_samples")
    if heterogeneous_batch_count < limits.min_heterogeneous_batches:
        reasons.append("insufficient_heterogeneous_batches")
    if _has_consecutive_weak_batches(recent_ratios, limits):
        reasons.append("consecutive_weak_heterogeneous_batches")
    if routing_changed_count:
        reasons.append("shadow_routing_changed")
    if not guard.passed:
        reasons.append("quality_regression_guard_failed")

    any_family_eligible = any(
        family.state == PromotionState.ELIGIBLE_FOR_BOUNDED_STEERING
        for family in families
    )
    global_gate_satisfied = not reasons and any_family_eligible

    return PromotionDecision(
        state=(
            PromotionState.ELIGIBLE_FOR_BOUNDED_STEERING
            if global_gate_satisfied
            else PromotionState.SHADOW_ONLY
        ),
        total_outcomes=len(items),
        total_scorable=len(scorable),
        heterogeneous_batch_count=max(0, heterogeneous_batch_count),
        recent_batch_supported_ratios=recent_ratios,
        quality_guard_passed=guard.passed,
        routing_changed_count=routing_changed_count,
        families=families,
        reason_codes=reasons or ["global_gate_satisfied"],
    )
