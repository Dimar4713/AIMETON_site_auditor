from scripts.search_gap_query_replay_report import build_replay_report


def test_replay_report_builds_regime_gap_bucket_from_result_rows():
    report = build_replay_report({
        "cases": [
            {
                "mission_id": "m1",
                "attempt_id": "a1",
                "gap_code": "sparse_yield",
                "effective_regime": "balanced",
                "suggested_follow_up_query": "dentistry Krasnoyarsk contacts",
                "observed_query": "dentistry Krasnoyarsk contacts",
                "baseline_domains": ["known.example"],
                "results": [
                    {"url": "https://known.example/a", "qualified": True},
                    {"url": "https://new.example/a", "qualified": True, "direct_or_official": True},
                ],
            }
        ]
    })
    assert report["evidence_kind"] == "search_gap_query_replay"
    assert report["case_count"] == 1
    assert report["record_count"] == 1
    assert report["assessments"][0]["verdict"] == "supported"
    assert report["buckets"][0]["effective_regime"] == "balanced"
    assert report["buckets"][0]["gap_code"] == "sparse_yield"
    assert report["routing_changed"] is False
    assert report["steering_enabled"] is False
    assert report["promotion_activated"] is False
