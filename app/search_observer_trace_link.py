from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.search_observer_llm import ObserverAction
from app.search_observer_multiwave import (
    DirectionWaveOutcomeSnapshot,
    derive_later_direction_marginal_yield,
)
from app.search_observer_scoring import (
    OfflineRecommendationEvidence,
    ObserverRuntimeEvidence,
    RecommendationOutcome,
    score_offline_evidence,
)


class TraceLinkModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PersistedRecommendationEvidence(TraceLinkModel):
    """One bounded, persisted shadow recommendation ready for later linkage."""

    mission_id: str = Field(min_length=1, max_length=120)
    attempt_id: str = Field(min_length=1, max_length=120)
    source_wave_index: int = Field(ge=1)
    direction_index: int = Field(ge=0)
    action: ObserverAction
    confidence: float = Field(ge=0.0, le=1.0)
    runtime: ObserverRuntimeEvidence
    routing_changed: bool = False


def build_offline_recommendation_evidence(
    *,
    recommendation: PersistedRecommendationEvidence,
    source_wave: DirectionWaveOutcomeSnapshot,
    later_wave: DirectionWaveOutcomeSnapshot,
) -> OfflineRecommendationEvidence:
    """Link one direction-level recommendation to that direction's later wave.

    Attempt-level/global wave totals are deliberately not accepted here. This
    prevents global later yield from being over-attributed to every persisted
    direction recommendation.
    """
    if recommendation.routing_changed:
        raise ValueError("trace_link_requires_shadow_routing_unchanged")
    if (
        recommendation.mission_id != source_wave.mission_id
        or recommendation.attempt_id != source_wave.attempt_id
    ):
        raise ValueError("recommendation_source_wave_identity_mismatch")
    if recommendation.source_wave_index != source_wave.wave_index:
        raise ValueError("recommendation_source_wave_index_mismatch")
    if recommendation.direction_index != source_wave.direction_index:
        raise ValueError("recommendation_source_direction_mismatch")
    if recommendation.direction_index != later_wave.direction_index:
        raise ValueError("recommendation_later_direction_mismatch")

    outcome = derive_later_direction_marginal_yield(source_wave, later_wave)
    return OfflineRecommendationEvidence(
        mission_id=recommendation.mission_id,
        attempt_id=recommendation.attempt_id,
        direction_index=recommendation.direction_index,
        action=recommendation.action,
        confidence=recommendation.confidence,
        runtime=recommendation.runtime,
        outcome=outcome,
    )


def score_trace_linked_recommendation(
    *,
    recommendation: PersistedRecommendationEvidence,
    source_wave: DirectionWaveOutcomeSnapshot,
    later_wave: DirectionWaveOutcomeSnapshot,
) -> RecommendationOutcome:
    """Build and score direction-lineaged evidence with no runtime side effects."""
    evidence = build_offline_recommendation_evidence(
        recommendation=recommendation,
        source_wave=source_wave,
        later_wave=later_wave,
    )
    return score_offline_evidence(evidence)
