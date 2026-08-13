import pytest

from app.search_regime_utility import build_regime_utility_evidence


def test_precision_utility_reports_quality_and_waste_vector_without_weights():
    evidence = build_regime_utility_evidence(
        "precision",
        raw_results=20,
        unique_candidates=10,
        qualified_candidates=6,
        direct_or_official_candidates=3,
        duplicate_results=2,
        excluded_results=1,
    )

    assert evidence.evidence_complete is True
    assert evidence.reason_code == "precision_vector_complete"
    assert evidence.metrics == {
        "qualified_per_unique": 0.6,
        "direct_or_official_per_qualified": 0.5,
        "duplicate_or_excluded_waste_per_raw": 0.15,
    }


def test_balanced_utility_keeps_uniqueness_dimension():
    evidence = build_regime_utility_evidence(
        "balanced",
        raw_results=20,
        unique_candidates=12,
        qualified_candidates=6,
        direct_or_official_candidates=3,
        duplicate_results=2,
        excluded_results=1,
    )

    assert evidence.evidence_complete is True
    assert evidence.metrics["unique_per_raw"] == 0.6


def test_discovery_utility_fails_closed_without_novelty_evidence():
    evidence = build_regime_utility_evidence(
        "discovery",
        raw_results=20,
        unique_candidates=12,
        qualified_candidates=4,
        direct_or_official_candidates=1,
        duplicate_results=4,
        excluded_results=2,
    )

    assert evidence.evidence_complete is False
    assert evidence.reason_code == "discovery_evidence_incomplete"
    assert "novel_entities_per_unique" not in evidence.metrics


def test_discovery_utility_reports_novelty_and_uncertainty_vector_when_complete():
    evidence = build_regime_utility_evidence(
        "discovery",
        raw_results=20,
        unique_candidates=10,
        qualified_candidates=4,
        direct_or_official_candidates=1,
        duplicate_results=4,
        excluded_results=2,
        novel_entities=3,
        rare_hits=2,
        unique_evidence_items=5,
        uncertainty_reduction=0.4,
    )

    assert evidence.evidence_complete is True
    assert evidence.reason_code == "discovery_vector_complete"
    assert evidence.metrics["novel_entities_per_unique"] == 0.3
    assert evidence.metrics["rare_hits_per_unique"] == 0.2
    assert evidence.metrics["unique_evidence_items_per_raw"] == 0.25
    assert evidence.metrics["uncertainty_reduction"] == 0.4


def test_regime_utility_rejects_invalid_uncertainty_reduction():
    with pytest.raises(ValueError, match="uncertainty_reduction_out_of_range"):
        build_regime_utility_evidence(
            "discovery",
            raw_results=1,
            unique_candidates=1,
            qualified_candidates=1,
            direct_or_official_candidates=1,
            duplicate_results=0,
            excluded_results=0,
            novel_entities=1,
            rare_hits=1,
            unique_evidence_items=1,
            uncertainty_reduction=1.1,
        )


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"unique_candidates": 11}, "unique_candidates_exceed_raw_results"),
        ({"qualified_candidates": 7}, "qualified_candidates_exceed_unique_candidates"),
        (
            {"direct_or_official_candidates": 7},
            "direct_or_official_candidates_exceed_qualified_candidates",
        ),
        (
            {"duplicate_results": 8, "excluded_results": 3},
            "duplicate_and_excluded_exceed_raw_results",
        ),
    ],
)
def test_regime_utility_rejects_impossible_funnel_counts(override, reason):
    values = {
        "raw_results": 10,
        "unique_candidates": 6,
        "qualified_candidates": 4,
        "direct_or_official_candidates": 2,
        "duplicate_results": 2,
        "excluded_results": 1,
    }
    values.update(override)

    with pytest.raises(ValueError, match=reason):
        build_regime_utility_evidence("balanced", **values)


def test_discovery_utility_rejects_novelty_counts_above_unique_candidates():
    with pytest.raises(ValueError, match="novel_entities_exceed_unique_candidates"):
        build_regime_utility_evidence(
            "discovery",
            raw_results=10,
            unique_candidates=4,
            qualified_candidates=2,
            direct_or_official_candidates=1,
            duplicate_results=2,
            excluded_results=1,
            novel_entities=5,
            rare_hits=2,
            unique_evidence_items=3,
            uncertainty_reduction=0.2,
        )
