from app.search_gap_hindsight import (
    GapHindsightEvidence,
    GapHindsightVerdict,
    assess_gap_hindsight,
)


def evidence(**updates):
    base = dict(
        added_raw_results=0,
        added_unique_domains=0,
        added_qualified_candidates=0,
        added_direct_or_official_candidates=0,
        duplicate_results=0,
        excluded_results=0,
    )
    base.update(updates)
    return GapHindsightEvidence(**base)


def test_sparse_gap_is_supported_only_by_new_unique_or_qualified_yield():
    result = assess_gap_hindsight(
        gap_code="sparse_yield",
        effective_regime="balanced",
        evidence=evidence(added_raw_results=4, added_unique_domains=2),
    )
    assert result.verdict == GapHindsightVerdict.SUPPORTED
    assert result.routing_changed is False
    assert result.steering_enabled is False


def test_duplicate_pressure_requires_lower_waste_and_new_unique_domains():
    result = assess_gap_hindsight(
        gap_code="duplicate_or_excluded_pressure",
        effective_regime="precision",
        evidence=evidence(
            added_raw_results=10,
            added_unique_domains=3,
            duplicate_results=5,
            excluded_results=1,
        ),
    )
    assert result.verdict == GapHindsightVerdict.CONTRADICTED


def test_duplicate_pressure_repeat_only_follow_up_is_contradicted():
    result = assess_gap_hindsight(
        gap_code="duplicate_or_excluded_pressure",
        effective_regime="balanced",
        evidence=evidence(
            added_raw_results=8,
            added_unique_domains=0,
            duplicate_results=0,
            excluded_results=0,
        ),
    )
    assert result.verdict == GapHindsightVerdict.CONTRADICTED
    assert result.reason_code == "follow_up_added_no_new_unique_domains"


def test_region_gap_closes_only_with_explicit_region_evidence():
    result = assess_gap_hindsight(
        gap_code="region_confirmation_missing",
        effective_regime="balanced",
        evidence=evidence(
            added_raw_results=5,
            added_qualified_candidates=2,
            region_confirmed_candidates=0,
        ),
    )
    assert result.verdict == GapHindsightVerdict.CONTRADICTED


def test_discovery_without_novelty_evidence_is_not_scorable():
    result = assess_gap_hindsight(
        gap_code="discovery_novelty_unmeasured",
        effective_regime="discovery",
        evidence=evidence(added_raw_results=20, added_unique_domains=10),
    )
    assert result.verdict == GapHindsightVerdict.NOT_SCORABLE


def test_discovery_support_requires_explicit_novel_or_rare_hit():
    result = assess_gap_hindsight(
        gap_code="discovery_novelty_unmeasured",
        effective_regime="discovery",
        evidence=evidence(
            added_raw_results=3,
            added_unique_domains=2,
            novel_entities=1,
            rare_hits=0,
        ),
    )
    assert result.verdict == GapHindsightVerdict.SUPPORTED
