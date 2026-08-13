import pytest

from app.search_observer_llm import ObserverAction
from app.search_observer_scoring import ObservedMarginalYield, RecommendationOutcome, RecommendationVerdict
from app.search_regime_calibration import RegimeCalibrationRecord, summarize_regime_calibration
from app.search_regime_utility import build_regime_utility_evidence


def _outcome(verdict, score, routing_changed=False):
    return RecommendationOutcome(
        mission_id="m", attempt_id="a", direction_index=0,
        action=ObserverAction.CONTINUE, confidence=0.8,
        outcome=ObservedMarginalYield(
            added_queries=1, added_raw_results=10, added_unique_domains=5,
            added_qualified_candidates=4, added_direct_or_official_candidates=2,
            duplicate_results=1, excluded_results=1, latency_ms=100, cost_rub=0.0,
        ),
        verdict=verdict, score=score, reason_code="test", routing_changed=routing_changed,
    )


def _utility(regime, complete=True):
    kwargs = dict(
        raw_results=10, unique_candidates=6, qualified_candidates=4,
        direct_or_official_candidates=2, duplicate_results=2, excluded_results=1,
    )
    if regime == "discovery" and complete:
        kwargs.update(novel_entities=2, rare_hits=1, unique_evidence_items=3, uncertainty_reduction=0.25)
    return build_regime_utility_evidence(regime, **kwargs)


def _record(regime, verdict, score, complete=True):
    return RegimeCalibrationRecord(
        requested_regime="auto", effective_regime=regime,
        regime_reason=f"{regime}_reason", outcome=_outcome(verdict, score),
        utility=_utility(regime, complete),
    )


def test_summary_segments_legacy_hindsight_by_effective_regime():
    summary = summarize_regime_calibration([
        _record("precision", RecommendationVerdict.SUPPORTED, 0.4),
        _record("precision", RecommendationVerdict.CONTRADICTED, -0.2),
        _record("balanced", RecommendationVerdict.SUPPORTED, 0.2),
    ])
    assert summary["precision"]["record_count"] == 2
    assert summary["precision"]["legacy_supported_ratio"] == 0.5
    assert summary["precision"]["legacy_mean_score"] == 0.1
    assert summary["balanced"]["record_count"] == 1
    assert summary["discovery"]["record_count"] == 0


def test_incomplete_discovery_utility_stays_visible_not_promoted_to_complete():
    summary = summarize_regime_calibration([
        _record("discovery", RecommendationVerdict.INCONCLUSIVE, 0.0, complete=False)
    ])
    discovery = summary["discovery"]
    assert discovery["utility_evidence_complete_count"] == 0
    assert discovery["utility_evidence_incomplete_count"] == 1
    assert discovery["mean_utility_metrics"] == {}


def test_summary_exposes_mean_regime_utility_vector():
    summary = summarize_regime_calibration([
        _record("precision", RecommendationVerdict.SUPPORTED, 0.4)
    ])
    precision = summary["precision"]
    assert precision["mean_utility_metrics"]["qualified_per_unique"] == 0.666667
    assert precision["regime_reason_counts"] == {"precision_reason": 1}
    assert precision["routing_changed_count"] == 0


def test_calibration_rejects_regime_mismatch():
    bad = RegimeCalibrationRecord(
        requested_regime="auto", effective_regime="precision", regime_reason="x",
        outcome=_outcome(RecommendationVerdict.SUPPORTED, 0.4), utility=_utility("balanced"),
    )
    with pytest.raises(ValueError, match="utility_regime_must_match_effective_regime"):
        summarize_regime_calibration([bad])


def test_calibration_rejects_routing_changed_outcome():
    bad = RegimeCalibrationRecord(
        requested_regime="auto", effective_regime="precision", regime_reason="x",
        outcome=_outcome(RecommendationVerdict.SUPPORTED, 0.4, True), utility=_utility("precision"),
    )
    with pytest.raises(ValueError, match="regime_calibration_requires_shadow_routing_unchanged"):
        summarize_regime_calibration([bad])
