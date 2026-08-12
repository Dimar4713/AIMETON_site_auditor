from __future__ import annotations

import time

from app.search_observer_llm import (
    DirectionRecommendation,
    ObserverAction,
    SearchObserverRecommendation,
    _record_shadow_observer_evidence,
    get_last_shadow_observer_evidence,
)


def descriptor() -> dict[str, str | bool | float]:
    return {
        "profile_name": "routerai-shadow-observer",
        "provider": "routerai",
        "model": "deepseek/deepseek-v3.2",
        "tier": "O1",
        "configured": True,
        "timeout_seconds": 20.0,
    }


def test_success_persists_bounded_direction_recommendations_for_offline_scoring():
    recommendation = SearchObserverRecommendation(
        sufficient_evidence=True,
        summary="bounded shadow advice",
        recommendations=[
            DirectionRecommendation(
                direction_index=0,
                action=ObserverAction.CONTINUE,
                confidence=0.81,
                rationale="productive direction",
            ),
            DirectionRecommendation(
                direction_index=1,
                action=ObserverAction.REFINE,
                confidence=0.73,
                rationale="high duplicate pressure",
                refined_queries=["refined one", "refined two"],
            ),
        ],
    )
    _record_shadow_observer_evidence(
        descriptor=descriptor(),
        started=time.perf_counter(),
        outcome="succeeded",
        recommendation=recommendation,
    )
    evidence = get_last_shadow_observer_evidence()
    assert evidence["observer_outcome"] == "succeeded"
    assert evidence["observer_recommendation_count"] == 2
    assert evidence["later_observation_state"] == "no_later_wave"
    assert evidence["recommendations"] == [
        {
            "direction_index": 0,
            "action": "continue",
            "confidence": 0.81,
            "rationale": "productive direction",
            "refined_queries": [],
            "later_observation_state": "no_later_wave",
        },
        {
            "direction_index": 1,
            "action": "refine",
            "confidence": 0.73,
            "rationale": "high duplicate pressure",
            "refined_queries": ["refined one", "refined two"],
            "later_observation_state": "no_later_wave",
        },
    ]
    assert "api_key" not in evidence
    assert "base_url" not in evidence


def test_timeout_persists_no_fake_recommendations():
    _record_shadow_observer_evidence(
        descriptor=descriptor(),
        started=time.perf_counter(),
        outcome="timeout",
        recommendation=None,
    )
    evidence = get_last_shadow_observer_evidence()
    assert evidence["observer_outcome"] == "timeout"
    assert evidence["schema_valid"] is False
    assert evidence["observer_recommendation_count"] == 0
    assert evidence["recommendations"] == []
    assert evidence["later_observation_state"] == "no_later_wave"
