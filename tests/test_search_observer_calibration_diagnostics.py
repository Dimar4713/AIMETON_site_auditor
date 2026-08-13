from scripts.search_observer_calibration_diagnostics import build_diagnostics


def _outcome(action, *, raw=20, qualified=4, direct=4, duplicate=0, excluded=0):
    return {
        "direction_index": 0,
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
