from app.search_observer_quality import QualityMetrics
from app.search_observer_quality_policy import derive_quality_first_guard


def metrics(*, qualified, direct, waste, latency=1000.0, cost=0.01):
    return QualityMetrics(
        sample_count=4,
        query_count=4,
        qualified_per_query=qualified,
        direct_or_official_per_query=direct,
        waste_ratio=waste,
        latency_ms_per_query=latency,
        cost_rub_per_query=cost,
    )


def test_quality_first_policy_allows_more_resource_use_when_quality_does_not_regress():
    baseline = metrics(qualified=4.0, direct=3.0, waste=0.20, latency=1000.0, cost=0.01)
    candidate = metrics(qualified=5.0, direct=4.0, waste=0.20, latency=5000.0, cost=0.08)
    guard = derive_quality_first_guard(
        baseline=baseline,
        candidate=candidate,
        resource_policy_compliant=True,
    )
    assert guard.evidence_complete is True
    assert guard.passed is True


def test_quality_first_policy_blocks_any_qualified_yield_regression():
    baseline = metrics(qualified=4.0, direct=3.0, waste=0.20)
    candidate = metrics(qualified=3.99, direct=3.5, waste=0.20)
    guard = derive_quality_first_guard(
        baseline=baseline,
        candidate=candidate,
        resource_policy_compliant=True,
    )
    assert guard.qualified_yield_regressed is True
    assert guard.passed is False


def test_quality_first_policy_blocks_any_direct_yield_regression():
    baseline = metrics(qualified=4.0, direct=3.0, waste=0.20)
    candidate = metrics(qualified=4.5, direct=2.99, waste=0.20)
    guard = derive_quality_first_guard(
        baseline=baseline,
        candidate=candidate,
        resource_policy_compliant=True,
    )
    assert guard.direct_or_official_yield_regressed is True
    assert guard.passed is False


def test_quality_first_policy_blocks_any_waste_increase():
    baseline = metrics(qualified=4.0, direct=3.0, waste=0.20)
    candidate = metrics(qualified=5.0, direct=4.0, waste=0.200001)
    guard = derive_quality_first_guard(
        baseline=baseline,
        candidate=candidate,
        resource_policy_compliant=True,
    )
    assert guard.duplicate_or_excluded_waste_regressed is True
    assert guard.passed is False


def test_quality_first_policy_fails_closed_when_resource_envelope_unknown():
    baseline = metrics(qualified=4.0, direct=3.0, waste=0.20)
    candidate = metrics(qualified=5.0, direct=4.0, waste=0.20)
    guard = derive_quality_first_guard(
        baseline=baseline,
        candidate=candidate,
        resource_policy_compliant=None,
    )
    assert guard.evidence_complete is False
    assert guard.passed is False


def test_quality_first_policy_blocks_when_existing_hard_caps_fail():
    baseline = metrics(qualified=4.0, direct=3.0, waste=0.20)
    candidate = metrics(qualified=6.0, direct=5.0, waste=0.10, latency=9000.0, cost=0.50)
    guard = derive_quality_first_guard(
        baseline=baseline,
        candidate=candidate,
        resource_policy_compliant=False,
    )
    assert guard.latency_or_cost_outside_policy is True
    assert guard.passed is False
