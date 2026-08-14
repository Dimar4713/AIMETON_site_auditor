from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.search_observer_scoring import RecommendationOutcome, RecommendationVerdict
from app.search_regime_utility import RegimeUtilityEvidence, SearchRegime

RequestedSearchRegime = Literal["auto", "precision", "balanced", "discovery"]


@dataclass(frozen=True)
class RegimeCalibrationRecord:
    requested_regime: RequestedSearchRegime
    effective_regime: SearchRegime
    regime_reason: str
    outcome: RecommendationOutcome
    utility: RegimeUtilityEvidence

    def validate(self) -> None:
        if self.utility.regime != self.effective_regime:
            raise ValueError("utility_regime_must_match_effective_regime")
        if self.outcome.routing_changed:
            raise ValueError("regime_calibration_requires_shadow_routing_unchanged")
        if not self.regime_reason:
            raise ValueError("regime_calibration_requires_reason")


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 6) if values else 0.0


def summarize_regime_calibration(
    records: list[RegimeCalibrationRecord],
) -> dict[str, dict[str, object]]:
    """Segment retained Observer hindsight by effective regime without changing scoring."""
    grouped: dict[str, list[RegimeCalibrationRecord]] = {
        "precision": [],
        "balanced": [],
        "discovery": [],
    }
    for record in records:
        record.validate()
        grouped[record.effective_regime].append(record)

    summary: dict[str, dict[str, object]] = {}
    for regime, items in grouped.items():
        scorable = [
            item for item in items
            if item.outcome.verdict != RecommendationVerdict.NOT_SCORABLE
        ]
        decided = [
            item for item in scorable
            if item.outcome.verdict
            in {RecommendationVerdict.SUPPORTED, RecommendationVerdict.CONTRADICTED}
        ]
        supported = sum(
            item.outcome.verdict == RecommendationVerdict.SUPPORTED for item in decided
        )
        contradicted = sum(
            item.outcome.verdict == RecommendationVerdict.CONTRADICTED for item in decided
        )
        complete_utility = [item for item in items if item.utility.evidence_complete]
        metric_names = sorted(
            {
                name
                for item in complete_utility
                for name in item.utility.metrics
            }
        )
        mean_utility_metrics = {
            name: _mean(
                [
                    item.utility.metrics[name]
                    for item in complete_utility
                    if name in item.utility.metrics
                ]
            )
            for name in metric_names
        }
        reason_counts: dict[str, int] = {}
        for item in items:
            reason_counts[item.regime_reason] = reason_counts.get(item.regime_reason, 0) + 1

        summary[regime] = {
            "record_count": len(items),
            "scorable_count": len(scorable),
            "decided_count": len(decided),
            "supported_count": supported,
            "contradicted_count": contradicted,
            "legacy_supported_ratio": (
                round(supported / len(decided), 6) if decided else 0.0
            ),
            "legacy_mean_score": _mean([item.outcome.score for item in scorable]),
            "utility_evidence_complete_count": len(complete_utility),
            "utility_evidence_incomplete_count": len(items) - len(complete_utility),
            "utility_evidence_complete_ratio": (
                round(len(complete_utility) / len(items), 6) if items else 0.0
            ),
            "mean_utility_metrics": mean_utility_metrics,
            "regime_reason_counts": dict(sorted(reason_counts.items())),
            "routing_changed_count": sum(item.outcome.routing_changed for item in items),
        }
    return summary
