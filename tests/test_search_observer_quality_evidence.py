from app.search_observer_quality_evidence import load_shadow_quality_proxy


def test_shadow_proxy_recovers_source_later_and_marginal_metrics():
    payload = {
        "scenarios": [
            {
                "outcomes": [
                    {
                        "source_snapshot": {
                            "query_count": 1,
                            "raw_results": 10,
                            "qualified_candidates": 8,
                            "direct_or_official_candidates": 7,
                            "duplicate_results": 1,
                            "excluded_results": 1,
                            "latency_ms": 1000,
                            "cost_rub": 0.01,
                        },
                        "later_snapshot": {
                            "query_count": 2,
                            "raw_results": 30,
                            "qualified_candidates": 18,
                            "direct_or_official_candidates": 15,
                            "duplicate_results": 5,
                            "excluded_results": 3,
                            "latency_ms": 2200,
                            "cost_rub": 0.02,
                        },
                        "score": {
                            "outcome": {
                                "added_queries": 1,
                                "added_raw_results": 20,
                                "added_unique_domains": 10,
                                "added_qualified_candidates": 10,
                                "added_direct_or_official_candidates": 8,
                                "duplicate_results": 4,
                                "excluded_results": 2,
                                "latency_ms": 1200,
                                "cost_rub": 0.01,
                            }
                        },
                    }
                ]
            }
        ]
    }
    proxy = load_shadow_quality_proxy(payload)
    assert proxy.evidence_kind == "shadow_proxy"
    assert proxy.promotion_eligible is False
    assert proxy.reason_code == "shadow_proxy_not_steering_candidate"
    assert proxy.source.qualified_per_query == 8.0
    assert proxy.later.qualified_per_query == 9.0
    assert proxy.marginal.qualified_per_query == 10.0


def test_shadow_proxy_fails_closed_when_snapshots_are_missing():
    try:
        load_shadow_quality_proxy({"scenarios": [{"outcomes": [{}]}]})
    except ValueError as exc:
        assert str(exc) == "shadow_quality_proxy_requires_source_later_and_marginal_evidence"
    else:
        raise AssertionError("expected ValueError")
