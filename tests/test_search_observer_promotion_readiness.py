import pytest

from app.search_observer_quality_policy import QualityFirstPromotionPolicy
from scripts.search_observer_promotion_readiness import build_readiness


def retained_payload(*, routing_changed=False, include_score=True, include_quality=False):
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
    if include_quality:
        outcome["source_snapshot"] = {
            "query_count": 2,
            "raw_results": 20,
            "qualified_candidates": 5,
            "direct_or_official_candidates": 4,
            "duplicate_results": 4,
            "excluded_results": 2,
            "latency_ms": 400,
            "cost_rub": 0.02,
        }
        outcome["later_snapshot"] = {
            "query_count": 2,
            "raw_results": 20,
            "qualified_candidates": 8,
            "direct_or_official_candidates": 6,
            "duplicate_results": 6,
            "excluded_results": 2,
            "latency_ms": 350,
            "cost_rub": 0.02,
        }
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
    assert readiness["quality_policy_persisted"] is False
    assert readiness["quality_evidence_loaded"] is False
    assert readiness["decision"]["state"] == "shadow_only"
    assert readiness["decision"]["quality_evidence_complete"] is False
    assert "quality_evidence_missing" in readiness["decision"]["reason_codes"]


def test_admin_policy_and_retained_quality_build_complete_passing_guard():
    readiness = build_readiness(
        [retained_payload(include_quality=True)],
        heterogeneous_batch_count=1,
        recent_batch_supported_ratios=[1.0],
        quality_policy=QualityFirstPromotionPolicy(max_waste_ratio_increase=0.15),
        quality_policy_persisted=True,
        resource_policy_compliant=True,
    )

    assert readiness["quality_thresholds_supplied"] is True
    assert readiness["quality_policy_persisted"] is True
    assert readiness["quality_evidence_loaded"] is True
    assert readiness["resource_policy_compliant"] is True
    assert readiness["decision"]["quality_evidence_complete"] is True
    assert readiness["decision"]["quality_guard_passed"] is True
    assert readiness["decision"]["state"] == "shadow_only"
    assert readiness["promotion_activated"] is False
    assert "insufficient_total_samples" in readiness["decision"]["reason_codes"]


def test_unknown_resource_compliance_keeps_admin_policy_fail_closed():
    readiness = build_readiness(
        [retained_payload(include_quality=True)],
        heterogeneous_batch_count=1,
        recent_batch_supported_ratios=[1.0],
        quality_policy=QualityFirstPromotionPolicy(max_waste_ratio_increase=0.15),
        quality_policy_persisted=True,
        resource_policy_compliant=None,
    )

    assert readiness["quality_thresholds_supplied"] is True
    assert readiness["quality_evidence_loaded"] is True
    assert readiness["decision"]["quality_evidence_complete"] is False
    assert readiness["decision"]["quality_guard_passed"] is False
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
