from app.search_gap_hindsight import GapHindsightAssessment, GapHindsightVerdict
from app.search_gap_hindsight_aggregation import aggregate_gap_hindsight


def assessment(regime, gap, verdict):
    return GapHindsightAssessment(
        gap_code=gap,
        effective_regime=regime,
        verdict=verdict,
        reason_code="test",
    )


def test_aggregation_is_segmented_by_regime_and_gap():
    rows = aggregate_gap_hindsight([
        assessment("precision", "duplicate_or_excluded_pressure", GapHindsightVerdict.SUPPORTED),
        assessment("precision", "duplicate_or_excluded_pressure", GapHindsightVerdict.CONTRADICTED),
        assessment("discovery", "discovery_novelty_unmeasured", GapHindsightVerdict.SUPPORTED),
        assessment("discovery", "discovery_novelty_unmeasured", GapHindsightVerdict.NOT_SCORABLE),
    ])
    by_key = {(row.effective_regime, row.gap_code): row for row in rows}

    precision = by_key[("precision", "duplicate_or_excluded_pressure")]
    assert precision.total == 2
    assert precision.scorable == 2
    assert precision.support_rate == 0.5
    assert precision.contradiction_rate == 0.5

    discovery = by_key[("discovery", "discovery_novelty_unmeasured")]
    assert discovery.total == 2
    assert discovery.scorable == 1
    assert discovery.not_scorable == 1
    assert discovery.support_rate == 1.0


def test_aggregation_keeps_unscorable_evidence_visible():
    rows = aggregate_gap_hindsight([
        assessment("discovery", "discovery_novelty_unmeasured", GapHindsightVerdict.NOT_SCORABLE),
    ])
    assert rows[0].total == 1
    assert rows[0].scorable == 0
    assert rows[0].not_scorable == 1
    assert rows[0].support_rate == 0.0
    assert rows[0].contradiction_rate == 0.0


def test_empty_aggregation_is_empty():
    assert aggregate_gap_hindsight([]) == []
