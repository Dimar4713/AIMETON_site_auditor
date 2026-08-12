from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.search_observer_llm import ObserverAction


class ScoringModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RecommendationVerdict(StrEnum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    INCONCLUSIVE = "inconclusive"
    NOT_SCORABLE = "not_scorable"


class ObserverRuntimeOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    NOT_CONFIGURED = "not_configured"


class ObserverRuntimeEvidence(ScoringModel):
    """Secret-free runtime evidence for one advisory Observer evaluation."""

    profile_name: str = Field(min_length=1, max_length=120)
    provider: str = Field(min_length=1, max_length=120)
    model: str = Field(min_length=1, max_length=200)
    tier: str = Field(min_length=1, max_length=40)
    timeout_seconds: float = Field(gt=0.0, le=30.0)
    observer_latency_ms: int = Field(ge=0)
    observer_outcome: ObserverRuntimeOutcome
    schema_valid: bool
    observer_recommendation_count: int = Field(ge=0)
    routing_changed: bool = False


class ObservedMarginalYield(ScoringModel):
    """Later observed evidence used to score an earlier shadow recommendation.

    This model is descriptive only: it has no provider or routing capability.
    All fields represent deltas observed after the recommendation was recorded.
    """

    added_queries: int = Field(ge=0)
    added_raw_results: int = Field(ge=0)
    added_unique_domains: int = Field(ge=0)
    added_qualified_candidates: int = Field(ge=0)
    added_direct_or_official_candidates: int = Field(ge=0)
    duplicate_results: int = Field(ge=0)
    excluded_results: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    cost_rub: float = Field(ge=0.0)

    @property
    def useful_yield(self) -> int:
        return self.added_qualified_candidates + self.added_direct_or_official_candidates

    @property
    def waste_ratio(self) -> float:
        if self.added_raw_results <= 0:
            return 0.0
        wasted = min(self.added_raw_results, self.duplicate_results + self.excluded_results)
        return round(wasted / self.added_raw_results, 6)


class OfflineRecommendationEvidence(ScoringModel):
    """Trace-linked, read-only input for scoring one shadow recommendation."""

    mission_id: str = Field(min_length=1, max_length=120)
    attempt_id: str = Field(min_length=1, max_length=120)
    direction_index: int = Field(ge=0)
    action: ObserverAction
    confidence: float = Field(ge=0.0, le=1.0)
    runtime: ObserverRuntimeEvidence
    outcome: ObservedMarginalYield


class RecommendationOutcome(ScoringModel):
    mission_id: str = Field(min_length=1, max_length=120)
    attempt_id: str = Field(min_length=1, max_length=120)
    direction_index: int = Field(ge=0)
    action: ObserverAction
    confidence: float = Field(ge=0.0, le=1.0)
    outcome: ObservedMarginalYield
    verdict: RecommendationVerdict
    score: float = Field(ge=-1.0, le=1.0)
    reason_code: str = Field(min_length=1, max_length=80)
    routing_changed: bool = False


def _continuation_value(outcome: ObservedMarginalYield) -> float:
    """Deterministic normalized value of spending another bounded search step."""
    if outcome.added_queries == 0:
        return 0.0
    useful_per_query = outcome.useful_yield / outcome.added_queries
    uniqueness_bonus = min(1.0, outcome.added_unique_domains / max(1, outcome.added_queries * 3))
    waste_penalty = outcome.waste_ratio
    cost_penalty = min(1.0, outcome.cost_rub / max(0.01, outcome.added_queries * 0.02))
    value = (0.5 * min(1.0, useful_per_query / 2.0)) + (0.25 * uniqueness_bonus)
    value -= 0.2 * waste_penalty
    value -= 0.05 * cost_penalty
    return max(-1.0, min(1.0, round(value, 6)))


def score_recommendation(
    *,
    mission_id: str,
    attempt_id: str,
    direction_index: int,
    action: ObserverAction,
    confidence: float,
    outcome: ObservedMarginalYield,
) -> RecommendationOutcome:
    """Score shadow advice against later observed yield without changing routing.

    `escalate` is intentionally not scored here because its value depends on a
    separate economic/authorization decision rather than ordinary marginal yield.
    """
    if action == ObserverAction.ESCALATE:
        return RecommendationOutcome(
            mission_id=mission_id,
            attempt_id=attempt_id,
            direction_index=direction_index,
            action=action,
            confidence=confidence,
            outcome=outcome,
            verdict=RecommendationVerdict.NOT_SCORABLE,
            score=0.0,
            reason_code="economic_gate_required",
        )

    if outcome.added_queries == 0:
        return RecommendationOutcome(
            mission_id=mission_id,
            attempt_id=attempt_id,
            direction_index=direction_index,
            action=action,
            confidence=confidence,
            outcome=outcome,
            verdict=RecommendationVerdict.INCONCLUSIVE,
            score=0.0,
            reason_code="no_later_search_observation",
        )

    value = _continuation_value(outcome)
    productive = value >= 0.35
    weak = value <= 0.12
    high_waste = outcome.waste_ratio >= 0.6

    if action in {ObserverAction.CONTINUE, ObserverAction.BOOST}:
        supported = productive
        contradicted = weak or high_waste
        reason_supported = "later_yield_supports_continuation"
        reason_contradicted = "later_yield_does_not_support_continuation"
    elif action == ObserverAction.STOP:
        supported = weak or high_waste
        contradicted = productive
        reason_supported = "later_yield_supports_stop"
        reason_contradicted = "later_yield_contradicts_stop"
    elif action in {ObserverAction.REFINE, ObserverAction.SLOW}:
        supported = (outcome.useful_yield > 0 and high_waste) or (0.12 < value < 0.35)
        contradicted = productive and not high_waste
        reason_supported = "later_yield_supports_adjustment"
        reason_contradicted = "later_yield_does_not_need_adjustment"
    else:
        supported = False
        contradicted = False
        reason_supported = "unsupported_action_family"
        reason_contradicted = "unsupported_action_family"

    magnitude = min(1.0, max(0.1, abs(value - 0.25) * 1.5))
    weighted = round(magnitude * max(0.25, confidence), 6)
    if supported:
        verdict = RecommendationVerdict.SUPPORTED
        score = weighted
        reason = reason_supported
    elif contradicted:
        verdict = RecommendationVerdict.CONTRADICTED
        score = -weighted
        reason = reason_contradicted
    else:
        verdict = RecommendationVerdict.INCONCLUSIVE
        score = 0.0
        reason = "later_yield_ambiguous"

    return RecommendationOutcome(
        mission_id=mission_id,
        attempt_id=attempt_id,
        direction_index=direction_index,
        action=action,
        confidence=confidence,
        outcome=outcome,
        verdict=verdict,
        score=score,
        reason_code=reason,
        routing_changed=False,
    )


def score_offline_evidence(evidence: OfflineRecommendationEvidence) -> RecommendationOutcome:
    """Score already-recorded evidence only; never calls providers or changes routing."""
    if evidence.runtime.routing_changed:
        raise ValueError("offline_scoring_requires_shadow_routing_unchanged")
    if evidence.runtime.observer_outcome != ObserverRuntimeOutcome.SUCCEEDED:
        raise ValueError("recommendation_requires_succeeded_observer_runtime")
    if not evidence.runtime.schema_valid:
        raise ValueError("recommendation_requires_schema_valid_observer_runtime")
    if evidence.runtime.observer_recommendation_count <= 0:
        raise ValueError("recommendation_requires_recorded_observer_recommendation")
    return score_recommendation(
        mission_id=evidence.mission_id,
        attempt_id=evidence.attempt_id,
        direction_index=evidence.direction_index,
        action=evidence.action,
        confidence=evidence.confidence,
        outcome=evidence.outcome,
    )


def summarize_recommendation_scores(
    outcomes: list[RecommendationOutcome],
) -> dict[str, float | int]:
    scorable = [item for item in outcomes if item.verdict != RecommendationVerdict.NOT_SCORABLE]
    decided = [
        item
        for item in scorable
        if item.verdict in {RecommendationVerdict.SUPPORTED, RecommendationVerdict.CONTRADICTED}
    ]
    supported = sum(item.verdict == RecommendationVerdict.SUPPORTED for item in decided)
    return {
        "recommendation_count": len(outcomes),
        "scorable_count": len(scorable),
        "decided_count": len(decided),
        "supported_count": supported,
        "precision": round(supported / len(decided), 6) if decided else 0.0,
        "mean_score": round(sum(item.score for item in scorable) / len(scorable), 6) if scorable else 0.0,
        "routing_changed_count": sum(item.routing_changed for item in outcomes),
    }


def summarize_observer_runtime(evidence: list[ObserverRuntimeEvidence]) -> dict[str, float | int]:
    """Summarize advisory runtime reliability without treating fail-open as search failure."""
    total = len(evidence)
    succeeded = sum(item.observer_outcome == ObserverRuntimeOutcome.SUCCEEDED for item in evidence)
    timed_out = sum(item.observer_outcome == ObserverRuntimeOutcome.TIMEOUT for item in evidence)
    unavailable = sum(item.observer_outcome == ObserverRuntimeOutcome.UNAVAILABLE for item in evidence)
    not_configured = sum(item.observer_outcome == ObserverRuntimeOutcome.NOT_CONFIGURED for item in evidence)
    mean_latency = round(sum(item.observer_latency_ms for item in evidence) / total, 3) if total else 0.0
    return {
        "evaluation_count": total,
        "succeeded_count": succeeded,
        "timeout_count": timed_out,
        "unavailable_count": unavailable,
        "not_configured_count": not_configured,
        "success_rate": round(succeeded / total, 6) if total else 0.0,
        "timeout_rate": round(timed_out / total, 6) if total else 0.0,
        "mean_observer_latency_ms": mean_latency,
        "routing_changed_count": sum(item.routing_changed for item in evidence),
    }
