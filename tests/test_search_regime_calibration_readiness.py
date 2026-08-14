import pytest

from app.search_observer_llm import ObserverAction
from app.search_observer_scoring import ObservedMarginalYield, RecommendationOutcome, RecommendationVerdict
from app.search_regime_calibration import RegimeCalibrationRecord, summarize_regime_calibration
from app.search_regime_utility import build_regime_utility_evidence


def _outcome(verdict):
    return RecommendationOutcome(
        mission_id="m", attempt_id="a", direction_index=0,
        action=ObserverAction.CONTINUE, confidence=0.8,
        outcome=ObservedMarginalYield(
            added_queries=1, added_raw_results=4, added_unique_domains=2,
            added_qualified_candidates=1, added_direct_or_official_candidates=1,
            duplicate_results=1, excluded_results=0, latency_ms=1, cost_rub=0.0,
        ),
        verdict=verdict, score=0.1 if verdict == RecommendationVerdict.SUPPORTED else 0.0,
        reason_code="test", routing_changed=False,
    )


def _utility(regime):
    kwargs = dict(raw_results=4, unique_candidates=2, qualified_candidates=1,
                  direct_or_official_candidates=1, duplicate_results=1, excluded_results=0)
    if regime == "discovery":
        kwargs.update(novel_entities=1, rare_hits=1, unique_evidence_items=1, uncertainty_reduction=0.25)
    return build_regime_utility_evidence(regime, **kwargs)


def test_explicit_requested_regime_must_match_effective():
    record = RegimeCalibrationRecord(
        requested_regime="precision", effective_regime="balanced", regime_reason="x",
        outcome=_outcome(RecommendationVerdict.SUPPORTED), utility=_utility("balanced"),
    )
    with pytest.raises(ValueError, match="explicit_requested_regime_must_match_effective_regime"):
        summarize_regime_calibration([record])


def test_auto_may_resolve_to_discovery_and_be_calibration_ready():
    record = RegimeCalibrationRecord(
        requested_regime="auto", effective_regime="discovery", regime_reason="rarity_or_sparsity",
        outcome=_outcome(RecommendationVerdict.SUPPORTED), utility=_utility("discovery"),
    )
    summary = summarize_regime_calibration([record])
    assert summary["discovery"]["calibration_ready_count"] == 1
    assert summary["discovery"]["calibration_ready_ratio"] == 1.0


def test_not_scorable_record_is_not_calibration_ready():
    record = RegimeCalibrationRecord(
        requested_regime="precision", effective_regime="precision", regime_reason="user_override",
        outcome=_outcome(RecommendationVerdict.NOT_SCORABLE), utility=_utility("precision"),
    )
    summary = summarize_regime_calibration([record])
    assert summary["precision"]["utility_evidence_complete_count"] == 1
    assert summary["precision"]["calibration_ready_count"] == 0
