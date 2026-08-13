from scripts.search_observer_calibration_diagnostics import build_diagnostics


def _outcome(
    action,
    *,
    direction_index=0,
    raw=20,
    qualified=4,
    direct=4,
    duplicate=0,
    excluded=0,
    source_raw=10,
    source_qualified=3,
    source_direct=2,
    source_duplicate=2,
    source_excluded=1,
):
    return {
        "direction_index": direction_index,
        "source_snapshot": {
            "query_count": 2,
            "raw_results": source_raw,
            "qualified_candidates": source_qualified,
            "direct_or_official_candidates": source_direct,
            "duplicate_results": source_duplicate,
            "excluded_results": source_excluded,
            "latency_ms": 100,
            "cost_rub": 0.0,
        },
        "score": {
            "action": action,
            "routing_changed": False,
            "outcome": {
                "added_queries": 1,
                "added_raw_results": raw,
                "added_unique_domains": 5,
                "added_qualified_candidates": qualified,
                "added_direct_or_official_candidates": direct,
                "duplicate_results": duplicate,
                "excluded_results": excluded,
                "latency_ms": 100,
                "cost_rub": 0.0,
            },
        },
    }


def _observer_input():
    return {
        "routing_changed": False,
        "telemetry": {
            "query_count": 2,
            "result_count": 18,
            "unique_domain_count": 12,
            "duplicate_domain_ratio": 0.333333,
            "provider_result_counts": {"provider_a": 10, "provider_b": 8},
            "attempt_states": {"succeeded": 4},
            "latency_ms_total": 500,
            "degraded_attempts": 1,
            "total_cost_by_currency": {"RUB": "0.02"},
            "directions": [
                {
                    "query": "query one",
                    "result_count": 10,
                    "unique_domain_count": 8,
                    "duplicate_domain_ratio": 0.2,
                    "provider_result_counts": {"provider_a": 6, "provider_b": 4},
                    "attempt_states": {"succeeded": 2},
                    "latency_ms_total": 240,
                    "degraded_attempts": 0,
                    "cache_hit": False,
                    "total_cost_by_currency": {"RUB": "0.01"},
                },
                {
                    "query": "query two",
                    "result_count": 8,
                    "unique_domain_count": 4,
                    "duplicate_domain_ratio": 0.5,
                    "provider_result_counts": {"provider_a": 4, "provider_b": 4},
                    "attempt_states": {"succeeded": 2},
                    "latency_ms_total": 260,
                    "degraded_attempts": 1,
                    "cache_hit": True,
                    "total_cost_by_currency": {"RUB": "0.01"},
                },
            ],
        },
    }


def test_build_diagnostics_categorizes_shadow_disagreements():
    payload = {
        "scenarios": [
            {"slug": "clean-refine", "outcomes": [_outcome("refine", duplicate=4, excluded=4)]},
            {"slug": "wasteful-continue", "outcomes": [_outcome("continue", duplicate=8, excluded=6)]},
            {"slug": "aligned-refine", "outcomes": [_outcome("refine", duplicate=8, excluded=6)]},
            {"slug": "no-gain", "outcomes": [_outcome("continue", qualified=0, direct=0)]},
        ]
    }

    result = build_diagnostics([payload])

    assert result["sample_count"] == 4
    assert result["aligned_count"] == 1
    assert result["disagreement_count"] == 3
    assert result["disagreement_ratio"] == 0.75
    assert result["cohorts"]["over_refine"]["count"] == 1
    assert result["cohorts"]["under_refine"]["count"] == 1
    assert result["cohorts"]["continue_without_gain"]["count"] == 1
    assert result["routing_changed"] is False
    assert result["steering_enabled"] is False
    assert result["promotion_eligible"] is False


def test_build_diagnostics_summarizes_source_wave_features_by_cohort():
    payload = {
        "scenarios": [
            {
                "slug": "over-refine",
                "outcomes": [
                    _outcome(
                        "refine",
                        duplicate=2,
                        excluded=2,
                        source_raw=12,
                        source_qualified=4,
                        source_direct=2,
                        source_duplicate=3,
                        source_excluded=1,
                    )
                ],
            }
        ]
    }

    result = build_diagnostics([payload])
    row = result["disagreements"][0]
    cohort = result["cohorts"]["over_refine"]

    assert row["source_waste_ratio"] == 0.333333
    assert row["source_raw_per_query"] == 6.0
    assert row["source_qualified_per_query"] == 2.0
    assert row["source_direct_or_official_per_query"] == 1.0
    assert cohort["mean_source_waste_ratio"] == 0.333333
    assert cohort["mean_source_raw_per_query"] == 6.0
    assert cohort["mean_source_qualified_per_query"] == 2.0
    assert cohort["mean_source_direct_or_official_per_query"] == 1.0
    assert cohort["source_feature_count"] == 1
    assert cohort["observer_input_feature_count"] == 0
    assert cohort["mean_observer_input_duplicate_domain_ratio"] is None


def test_build_diagnostics_uses_retained_observer_input_direction_features():
    payload = {
        "schema_version": 2,
        "scenarios": [
            {
                "slug": "v2-over-refine",
                "observer_input_telemetry": _observer_input(),
                "outcomes": [
                    _outcome("refine", direction_index=1, duplicate=2, excluded=2)
                ],
            }
        ],
    }

    result = build_diagnostics([payload])
    row = result["disagreements"][0]
    cohort = result["cohorts"]["over_refine"]

    assert row["observer_input_duplicate_domain_ratio"] == 0.5
    assert row["observer_input_unique_domain_count"] == 4
    assert row["observer_input_result_count"] == 8
    assert row["observer_input_degraded_attempts"] == 1
    assert row["observer_input_cache_hit"] is True
    assert row["observer_input_provider_result_counts"] == {
        "provider_a": 4,
        "provider_b": 4,
    }
    assert row["observer_input_attempt_states"] == {"succeeded": 2}
    assert cohort["observer_input_feature_count"] == 1
    assert cohort["mean_observer_input_duplicate_domain_ratio"] == 0.5
    assert cohort["mean_observer_input_unique_domain_count"] == 4.0
    assert cohort["mean_observer_input_result_count"] == 8.0
    assert cohort["mean_observer_input_degraded_attempts"] == 1.0
