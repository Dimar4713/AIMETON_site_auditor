from app.search_observer_llm import ObserverAction
from app.search_observer_scoring import ObservedMarginalYield, RecommendationOutcome, RecommendationVerdict
from app.search_regime_calibration import RegimeCalibrationRecord
from app.search_regime_calibration_export import build_regime_calibration_row
from app.search_regime_utility import build_regime_utility_evidence


def _record(verdict=RecommendationVerdict.SUPPORTED):
    outcome = RecommendationOutcome(
        mission_id="m1", attempt_id="a1", direction_index=2,
        action=ObserverAction.CONTINUE, confidence=0.8,
        outcome=ObservedMarginalYield(
            added_queries=1, added_raw_results=5, added_unique_domains=3,
            added_qualified_candidates=2, added_direct_or_official_candidates=1,
            duplicate_results=1, excluded_results=0, latency_ms=10, cost_rub=0.0,
        ),
        verdict=verdict, score=0.4 if verdict == RecommendationVerdict.SUPPORTED else 0.0,
        reason_code="legacy", routing_changed=False,
    )
    utility = build_regime_utility_evidence(
        "precision", raw_results=5, unique_candidates=3, qualified_candidates=2,
        direct_or_official_candidates=1, duplicate_results=1, excluded_results=0,
    )
    return RegimeCalibrationRecord(
        requested_regime="auto", effective_regime="precision",
        regime_reason="sufficient_high_quality_candidates", outcome=outcome, utility=utility,
    )


def test_export_row_preserves_trace_regime_legacy_and_utility_features():
    row = build_regime_calibration_row(_record())
    assert row["mission_id"] == "m1"
    assert row["direction_index"] == 2
    assert row["effective_regime"] == "precision"
    assert row["legacy_verdict"] == "supported"
    assert row["legacy_score"] == 0.4
    assert row["calibration_ready"] is True
    assert row["utility_qualified_per_unique"] == 0.666667
    assert row["routing_changed"] is False


def test_not_scorable_row_is_not_calibration_ready():
    row = build_regime_calibration_row(_record(RecommendationVerdict.NOT_SCORABLE))
    assert row["utility_evidence_complete"] is True
    assert row["calibration_ready"] is False
