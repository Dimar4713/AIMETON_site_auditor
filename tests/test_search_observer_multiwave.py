import pytest

from app.search_observer_multiwave import WaveOutcomeSnapshot, derive_later_marginal_yield


def snapshot(**overrides):
    values = {
        "mission_id": "hunt-test",
        "attempt_id": "corr-test",
        "wave_index": 1,
        "query_count": 2,
        "raw_results": 20,
        "unique_domains": 10,
        "qualified_candidates": 4,
        "direct_or_official_candidates": 3,
        "duplicate_results": 2,
        "excluded_results": 5,
        "latency_ms": 1200,
        "cost_rub": 0.02,
        "routing_changed": False,
    }
    values.update(overrides)
    return WaveOutcomeSnapshot(**values)


def test_derives_strictly_later_marginal_yield():
    earlier = snapshot()
    later = snapshot(
        wave_index=2,
        query_count=4,
        raw_results=34,
        unique_domains=16,
        qualified_candidates=7,
        direct_or_official_candidates=5,
        duplicate_results=4,
        excluded_results=8,
        latency_ms=2100,
        cost_rub=0.04,
    )
    observed = derive_later_marginal_yield(earlier, later)
    assert observed.added_queries == 2
    assert observed.added_raw_results == 14
    assert observed.added_unique_domains == 6
    assert observed.added_qualified_candidates == 3
    assert observed.added_direct_or_official_candidates == 2
    assert observed.duplicate_results == 2
    assert observed.excluded_results == 3
    assert observed.latency_ms == 900
    assert observed.cost_rub == 0.02


def test_rejects_same_wave_as_false_causal_evidence():
    with pytest.raises(ValueError, match="later_wave_required"):
        derive_later_marginal_yield(snapshot(), snapshot())


def test_rejects_identity_mismatch():
    with pytest.raises(ValueError, match="multiwave_identity_mismatch"):
        derive_later_marginal_yield(snapshot(), snapshot(wave_index=2, mission_id="hunt-other"))


def test_rejects_counter_regression():
    with pytest.raises(ValueError, match="multiwave_cumulative_counter_regression"):
        derive_later_marginal_yield(snapshot(), snapshot(wave_index=2, raw_results=19))


def test_rejects_routing_changed_evidence():
    with pytest.raises(ValueError, match="multiwave_scoring_requires_routing_unchanged"):
        derive_later_marginal_yield(snapshot(), snapshot(wave_index=2, routing_changed=True))
