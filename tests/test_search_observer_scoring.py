from app.search_observer_llm import ObserverAction
from app.search_observer_scoring import (
    ObservedMarginalYield,
    RecommendationVerdict,
    score_recommendation,
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
