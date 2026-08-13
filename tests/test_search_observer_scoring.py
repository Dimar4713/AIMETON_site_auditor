import pytest

from app.search_observer_llm import ObserverAction
from app.search_observer_scoring import (
    ObservedMarginalYield,
    ObserverRuntimeEvidence,
    ObserverRuntimeOutcome,
    OfflineRecommendationEvidence,
    RecommendationVerdict,
    assess_second_wave_shadow,
    score_offline_evidence,
    score_recommendation,
    summarize_observer_runtime,
    summarize_recommendation_scores,
)


def outcome(**overrides):
    values = {
        "added_queries": 2,
        "added_raw_results": 20,
        "added_unique_domains": 10,
        "added_qualified_candidates": 6,
        "added_direct_or_official_candidates": 4,
        "duplicate_results": 2,
        "excluded_results": 3,
        "latency_ms": 1200,
        "cost_rub": 0.02,
    }
    values.update(overrides)
    return ObservedMarginalYield(**values)


def runtime(**overrides):
    values = {
        "profile_name": "routerai-shadow-observer",
        "provider": "routerai",
        "model": "deepseek/deepseek-v3.2",
        "tier": "O1",
        "timeout_seconds": 20.0,
        "observer_latency_ms": 12000,
        "observer_outcome": ObserverRuntimeOutcome.SUCCEEDED,
        "schema_valid": True,
        "observer_recommendation_count": 2,
        "routing_changed": False,
    }
    values.update(overrides)
    return ObserverRuntimeEvidence(**values)


def score(action, observed, confidence=0.8):
    return score_recommendation(
        mission_id="hunt-test",
        attempt_id="corr-test",
        direction_index=0,
        action=action,
        confidence=confidence,
        outcome=observed,
    )


def test_continue_supported_by_productive_later_yield():
    item = score(ObserverAction.CONTINUE, outcome())
    assert item.verdict == RecommendationVerdict.SUPPORTED
    assert item.score > 0
    assert item.routing_changed is False


def test_stop_contradicted_by_productive_later_yield():
    item = score(ObserverAction.STOP, outcome())
    assert item.verdict == RecommendationVerdict.CONTRADICTED
    assert item.score < 0


def test_stop_supported_by_high_waste_low_yield():
    observed = outcome(
        added_unique_domains=1,
        added_qualified_candidates=0,
        added_direct_or_official_candidates=0,
        duplicate_results=11,
        excluded_results=7,
    )
    item = score(ObserverAction.STOP, observed)
    assert item.verdict == RecommendationVerdict.SUPPORTED
    assert item.score > 0


def test_refine_supported_when_some_signal_is_wasteful():
    observed = outcome(
        added_unique_domains=3,
        added_qualified_candidates=1,
        added_direct_or_official_candidates=0,
        duplicate_results=10,
        excluded_results=4,
    )
    item = score(ObserverAction.REFINE, observed)
    assert item.verdict == RecommendationVerdict.SUPPORTED


def test_refine_contradicted_by_clean_productive_yield():
    observed = outcome(duplicate_results=0, excluded_results=0)
    item = score(ObserverAction.REFINE, observed)
    assert item.verdict == RecommendationVerdict.CONTRADICTED


def test_no_later_queries_is_inconclusive():
    observed = outcome(
        added_queries=0,
        added_raw_results=0,
        added_unique_domains=0,
        added_qualified_candidates=0,
        added_direct_or_official_candidates=0,
        duplicate_results=0,
        excluded_results=0,
        latency_ms=0,
        cost_rub=0.0,
    )
    item = score(ObserverAction.CONTINUE, observed)
    assert item.verdict == RecommendationVerdict.INCONCLUSIVE
    assert item.score == 0


def test_escalate_remains_economic_gate_not_scorable():
    item = score(ObserverAction.ESCALATE, outcome())
    assert item.verdict == RecommendationVerdict.NOT_SCORABLE
    assert item.reason_code == "economic_gate_required"
    assert item.routing_changed is False


def test_shadow_second_wave_keeps_quality_gain_even_when_waste_is_high():
    observed = outcome(
        added_queries=1,
        added_raw_results=20,
        added_unique_domains=5,
        added_qualified_candidates=5,
        added_direct_or_official_candidates=2,
        duplicate_results=4,
        excluded_results=11,
    )
    decision = assess_second_wave_shadow(observed)
    assert decision.would_run_second_wave is True
    assert decision.quality_gain_observed is True
    assert decision.high_waste is True
    assert decision.waste_ratio == 0.75
    assert decision.reason_code == "shadow_run_quality_gain_refine_high_waste"
    assert decision.routing_changed is False


def test_shadow_second_wave_skips_high_waste_without_quality_gain():
    observed = outcome(
        added_queries=1,
        added_raw_results=20,
        added_unique_domains=1,
        added_qualified_candidates=0,
        added_direct_or_official_candidates=0,
        duplicate_results=9,
        excluded_results=6,
    )
    decision = assess_second_wave_shadow(observed)
    assert decision.would_run_second_wave is False
    assert decision.quality_gain_observed is False
    assert decision.high_waste is True
    assert decision.reason_code == "shadow_skip_no_quality_gain_high_waste"
    assert decision.routing_changed is False


def test_shadow_second_wave_clean_quality_gain_is_worth_running():
    decision = assess_second_wave_shadow(outcome(duplicate_results=0, excluded_results=0))
    assert decision.would_run_second_wave is True
    assert decision.high_waste is False
    assert decision.reason_code == "shadow_run_quality_gain_clean"


def test_shadow_second_wave_no_later_wave_is_not_run_candidate():
    decision = assess_second_wave_shadow(outcome(
        added_queries=0,
        added_raw_results=0,
        added_unique_domains=0,
        added_qualified_candidates=0,
        added_direct_or_official_candidates=0,
        duplicate_results=0,
        excluded_results=0,
        latency_ms=0,
        cost_rub=0.0,
    ))
    assert decision.would_run_second_wave is False
    assert decision.reason_code == "shadow_no_later_wave"
    assert decision.routing_changed is False


def test_summary_reports_precision_and_never_routing_changes():
    items = [
        score(ObserverAction.CONTINUE, outcome()),
        score(ObserverAction.STOP, outcome()),
        score(ObserverAction.ESCALATE, outcome()),
    ]
    summary = summarize_recommendation_scores(items)
    assert summary["recommendation_count"] == 3
    assert summary["scorable_count"] == 2
    assert summary["decided_count"] == 2
    assert summary["supported_count"] == 1
    assert summary["precision"] == 0.5
    assert summary["routing_changed_count"] == 0


def test_offline_evidence_scores_only_succeeded_shadow_runtime():
    evidence = OfflineRecommendationEvidence(
        mission_id="hunt-test",
        attempt_id="corr-test",
        direction_index=1,
        action=ObserverAction.REFINE,
        confidence=0.75,
        runtime=runtime(),
        outcome=outcome(duplicate_results=10, excluded_results=4, added_unique_domains=3,
                        added_qualified_candidates=1, added_direct_or_official_candidates=0),
    )
    item = score_offline_evidence(evidence)
    assert item.verdict == RecommendationVerdict.SUPPORTED
    assert item.routing_changed is False


def test_offline_evidence_rejects_timeout_as_recommendation_source():
    evidence = OfflineRecommendationEvidence(
        mission_id="hunt-test",
        attempt_id="corr-test",
        direction_index=0,
        action=ObserverAction.CONTINUE,
        confidence=0.8,
        runtime=runtime(
            observer_outcome=ObserverRuntimeOutcome.TIMEOUT,
            observer_latency_ms=20003,
            schema_valid=False,
            observer_recommendation_count=0,
        ),
        outcome=outcome(),
    )
    with pytest.raises(ValueError, match="recommendation_requires_succeeded_observer_runtime"):
        score_offline_evidence(evidence)


def test_runtime_summary_keeps_timeout_as_measurable_fail_open():
    summary = summarize_observer_runtime([
        runtime(observer_latency_ms=17027),
        runtime(observer_latency_ms=11965),
        runtime(observer_latency_ms=10843),
        runtime(
            observer_outcome=ObserverRuntimeOutcome.TIMEOUT,
            observer_latency_ms=20003,
            schema_valid=False,
            observer_recommendation_count=0,
        ),
    ])
    assert summary["evaluation_count"] == 4
    assert summary["succeeded_count"] == 3
    assert summary["timeout_count"] == 1
    assert summary["success_rate"] == 0.75
    assert summary["timeout_rate"] == 0.25
    assert summary["mean_observer_latency_ms"] == 14959.5
    assert summary["routing_changed_count"] == 0
