import pytest

from app.search_observer_llm import ObserverAction
from app.search_observer_multiwave import WaveOutcomeSnapshot
from app.search_observer_scoring import ObserverRuntimeEvidence, ObserverRuntimeOutcome, RecommendationVerdict
from app.search_observer_trace_link import (
    PersistedRecommendationEvidence,
    build_offline_recommendation_evidence,
    score_trace_linked_recommendation,
)


def runtime() -> ObserverRuntimeEvidence:
    return ObserverRuntimeEvidence(
        profile_name="routerai-shadow-observer",
        provider="routerai",
        model="deepseek/deepseek-v3.2",
        tier="O1",
        timeout_seconds=20.0,
        observer_latency_ms=12000,
        observer_outcome=ObserverRuntimeOutcome.SUCCEEDED,
        schema_valid=True,
        observer_recommendation_count=1,
        routing_changed=False,
    )


def wave(index: int, **overrides) -> WaveOutcomeSnapshot:
    values = {
        "mission_id": "hunt-1",
        "attempt_id": "corr-1",
        "wave_index": index,
        "query_count": 2 if index == 1 else 4,
        "raw_results": 20 if index == 1 else 36,
        "unique_domains": 10 if index == 1 else 18,
        "qualified_candidates": 6 if index == 1 else 10,
        "direct_or_official_candidates": 4 if index == 1 else 7,
        "duplicate_results": 2 if index == 1 else 5,
        "excluded_results": 3 if index == 1 else 6,
        "latency_ms": 1000 if index == 1 else 2200,
        "cost_rub": 0.02 if index == 1 else 0.04,
        "routing_changed": False,
    }
    values.update(overrides)
    return WaveOutcomeSnapshot(**values)


def recommendation(**overrides) -> PersistedRecommendationEvidence:
    values = {
        "mission_id": "hunt-1",
        "attempt_id": "corr-1",
        "source_wave_index": 1,
        "direction_index": 0,
        "action": ObserverAction.CONTINUE,
        "confidence": 0.8,
        "runtime": runtime(),
        "routing_changed": False,
    }
    values.update(overrides)
    return PersistedRecommendationEvidence(**values)


def test_trace_link_builds_genuinely_later_offline_evidence():
    evidence = build_offline_recommendation_evidence(
        recommendation=recommendation(),
        source_wave=wave(1),
        later_wave=wave(2),
    )
    assert evidence.outcome.added_queries == 2
    assert evidence.outcome.added_qualified_candidates == 4
    assert evidence.outcome.added_direct_or_official_candidates == 3
    assert evidence.runtime.routing_changed is False


def test_trace_link_can_feed_existing_deterministic_scorer():
    result = score_trace_linked_recommendation(
        recommendation=recommendation(),
        source_wave=wave(1),
        later_wave=wave(2),
    )
    assert result.verdict in {
        RecommendationVerdict.SUPPORTED,
        RecommendationVerdict.CONTRADICTED,
        RecommendationVerdict.INCONCLUSIVE,
    }
    assert result.routing_changed is False


def test_trace_link_rejects_recommendation_from_different_source_wave():
    with pytest.raises(ValueError, match="recommendation_source_wave_index_mismatch"):
        build_offline_recommendation_evidence(
            recommendation=recommendation(source_wave_index=2),
            source_wave=wave(1),
            later_wave=wave(2),
        )


def test_trace_link_rejects_recommendation_identity_mismatch():
    with pytest.raises(ValueError, match="recommendation_source_wave_identity_mismatch"):
        build_offline_recommendation_evidence(
            recommendation=recommendation(mission_id="hunt-other"),
            source_wave=wave(1),
            later_wave=wave(2),
        )


def test_trace_link_rejects_routing_changed_recommendation():
    with pytest.raises(ValueError, match="trace_link_requires_shadow_routing_unchanged"):
        build_offline_recommendation_evidence(
            recommendation=recommendation(routing_changed=True),
            source_wave=wave(1),
            later_wave=wave(2),
        )
