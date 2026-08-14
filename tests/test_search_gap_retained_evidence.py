import pytest

from app.search_gap_retained_evidence import RetainedGapOutcome, build_gap_hindsight_report


def record(*, gap="sparse_yield", regime="balanced", routing_changed=False, **evidence):
    base = dict(
        added_raw_results=0,
        added_unique_domains=0,
        added_qualified_candidates=0,
        added_direct_or_official_candidates=0,
        duplicate_results=0,
        excluded_results=0,
    )
    base.update(evidence)
    return RetainedGapOutcome(
        mission_id="m1",
        attempt_id="a1",
        follow_up_query="dentistry Krasnoyarsk contacts",
        gap_code=gap,
        effective_regime=regime,
        evidence=base,
        routing_changed=routing_changed,
    )


def test_report_preserves_assessments_and_regime_gap_buckets():
    report = build_gap_hindsight_report([
        record(added_raw_results=4, added_unique_domains=2),
        record(
            gap="discovery_novelty_unmeasured",
            regime="discovery",
            added_raw_results=3,
            added_unique_domains=2,
            novel_entities=1,
        ),
    ])
    assert report["record_count"] == 2
    assert len(report["assessments"]) == 2
    assert len(report["buckets"]) == 2
    assert report["routing_changed"] is False
    assert report["steering_enabled"] is False
    assert report["promotion_activated"] is False


def test_report_rejects_routing_changed_evidence():
    with pytest.raises(ValueError, match="gap_hindsight_requires_routing_unchanged"):
        build_gap_hindsight_report([record(routing_changed=True)])
