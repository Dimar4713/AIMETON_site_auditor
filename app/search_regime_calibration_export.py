from __future__ import annotations

from app.search_observer_scoring import RecommendationVerdict
from app.search_regime_calibration import RegimeCalibrationRecord


def build_regime_calibration_row(record: RegimeCalibrationRecord) -> dict[str, object]:
    """Flatten one validated shadow calibration record for offline analysis/export."""
    record.validate()
    outcome = record.outcome
    row: dict[str, object] = {
        "mission_id": outcome.mission_id,
        "attempt_id": outcome.attempt_id,
        "direction_index": outcome.direction_index,
        "action": outcome.action.value,
        "confidence": outcome.confidence,
        "requested_regime": record.requested_regime,
        "effective_regime": record.effective_regime,
        "regime_reason": record.regime_reason,
        "legacy_verdict": outcome.verdict.value,
        "legacy_score": outcome.score,
        "utility_evidence_complete": record.utility.evidence_complete,
        "utility_reason_code": record.utility.reason_code,
        "calibration_ready": (
            record.utility.evidence_complete
            and outcome.verdict != RecommendationVerdict.NOT_SCORABLE
        ),
        "routing_changed": outcome.routing_changed,
    }
    for name, value in sorted(record.utility.metrics.items()):
        row[f"utility_{name}"] = value
    return row


def build_regime_calibration_rows(
    records: list[RegimeCalibrationRecord],
) -> list[dict[str, object]]:
    """Build deterministic rows without calling providers, search, or LLMs."""
    return [build_regime_calibration_row(record) for record in records]
