from app.search_observer_quality import (
    QualityRegressionThresholds,
    derive_quality_guard,
    summarize_quality_metrics,
)
from app.search_observer_scoring import ObservedMarginalYield


def outcome(*, q=1, raw=10, qualified=5, direct=2, duplicates=1, excluded=1, latency=100, cost=0.01):
    return ObservedMarginalYield(
        added_queries=q,
        added_raw_results=raw,
        added_unique_domains=5,
        added_qualified_candidates=qualified,
        added_direct_or_official_candidates=direct,
        duplicate_results=duplicates,
        excluded_results=excluded,
        latency_ms=latency,
        cost_rub=cost,
    )


def test_quality_metrics_are_aggregated_per_query():
    metrics = summarize_quality_metrics([
        outcome(),
        outcome(q=2, raw=20, qualified=6, direct=4, duplicates=3, excluded=2, latency=300, cost=0.03),
    ])
    assert metrics.sample_count == 2
    assert metrics.query_count == 3
    assert metrics.qualified_per_query == 3.666667
    assert metrics.direct_or_official_per_query == 2.0
    assert metrics.waste_ratio == 0.233333
    assert metrics.latency_ms_per_query == 133.333333
    assert metrics.cost_rub_per_query == 0.013333


def test_missing_thresholds_leave_quality_guard_incomplete():
    baseline = summarize_quality_metrics([outcome()])
    candidate = summarize_quality_metrics([outcome()])
    comparison = derive_quality_guard(
        baseline=baseline,
        candidate=candidate,
        thresholds=None,
    )
    assert comparison.guard.evidence_complete is False
    assert comparison.guard.passed is False


def test_clean_comparison_passes_when_policy_thresholds_are_explicit():
    baseline = summarize_quality_metrics([outcome()])
    candidate = summarize_quality_metrics([
        outcome(qualified=5, direct=2, duplicates=1, excluded=1, latency=105, cost=0.0105)
    ])
    comparison = derive_quality_guard(
        baseline=baseline,
        candidate=candidate,
        thresholds=QualityRegressionThresholds(
            max_qualified_yield_drop_ratio=0.05,
            max_direct_or_official_yield_drop_ratio=0.05,
            max_waste_ratio_increase=0.05,
            max_latency_increase_ratio=0.10,
            max_cost_increase_ratio=0.10,
        ),
    )
    assert comparison.guard.evidence_complete is True
    assert comparison.guard.passed is True


def test_regressions_fail_quality_guard():
    baseline = summarize_quality_metrics([outcome()])
    candidate = summarize_quality_metrics([
        outcome(qualified=3, direct=1, duplicates=4, excluded=3, latency=150, cost=0.02)
    ])
    comparison = derive_quality_guard(
        baseline=baseline,
        candidate=candidate,
        thresholds=QualityRegressionThresholds(
            max_qualified_yield_drop_ratio=0.10,
            max_direct_or_official_yield_drop_ratio=0.10,
            max_waste_ratio_increase=0.10,
            max_latency_increase_ratio=0.20,
            max_cost_increase_ratio=0.20,
        ),
    )
    assert comparison.guard.evidence_complete is True
    assert comparison.guard.passed is False
    assert comparison.guard.qualified_yield_regressed is True
    assert comparison.guard.direct_or_official_yield_regressed is True
    assert comparison.guard.duplicate_or_excluded_waste_regressed is True
    assert comparison.guard.latency_or_cost_outside_policy is True
