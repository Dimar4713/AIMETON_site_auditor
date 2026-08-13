import pytest

from scripts.search_observer_promotion_readiness import build_readiness


def retained_payload(*, routing_changed=False, include_score=True):
    score = {
        "action": "slow",
        "confidence": 0.8,
        "outcome": {
            "added_queries": 1,
            "added_raw_results": 10,
            "added_unique_domains": 5,
            "added_qualified_candidates": 4,
            "added_direct_or_official_candidates": 2,
            "duplicate_results": 1,
            "excluded_results": 1,
            "latency_ms": 100,
            "cost_rub": 0.01,
        },
        "verdict": "supported",
        "score": 0.4,
        "reason_code": "test_supported",
        "routing_changed": routing_changed,
    }
    outcome = {"direction_index": 0}
    if include_score:
        outcome["score"] = score
    return {
        "scenarios": [
            {
                "slug": "dentistry-krasnoyarsk",
                "run_id": "run-1",
                "outcomes": [outcome],
            }
        ]
    }


def test_retained_readiness_is_fail_closed_without_quality_evidence():
    readiness = build_readiness(
        [retained_payload()],
        heterogeneous_batch_count=1,
        recent_batch_supported_ratios=[1.0],
    )

    assert readiness["evidence_kind"] == "search_observer_promotion_readiness"
    assert readiness["routing_changed"] is False
    assert readiness["steering_enabled"] is False
    assert readiness["promotion_activated"] is False
    assert readiness["quality_thresholds_supplied"] is False
    assert readiness["decision"]["state"] == "shadow_only"
    assert readiness["decision"]["quality_evidence_complete"] is False
    assert "quality_evidence_missing" in readiness["decision"]["reason_codes"]


def test_retained_routing_change_is_rejected_before_promotion_evaluation():
    with pytest.raises(ValueError, match="promotion_readiness_requires_routing_unchanged"):
        build_readiness(
            [retained_payload(routing_changed=True)],
            heterogeneous_batch_count=1,
            recent_batch_supported_ratios=[],
        )


def test_unscored_retained_evidence_is_rejected():
    with pytest.raises(ValueError, match="promotion_readiness_requires_scored_retained_evidence"):
        build_readiness(
            [retained_payload(include_score=False)],
            heterogeneous_batch_count=1,
            recent_batch_supported_ratios=[],
        )
