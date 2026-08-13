from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SearchRegime = Literal["precision", "balanced", "discovery"]


@dataclass(frozen=True)
class RegimeUtilityEvidence:
    regime: SearchRegime
    evidence_complete: bool
    reason_code: str
    metrics: dict[str, float]


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def build_regime_utility_evidence(
    regime: SearchRegime,
    *,
    raw_results: int,
    unique_candidates: int,
    qualified_candidates: int,
    direct_or_official_candidates: int,
    duplicate_results: int,
    excluded_results: int,
    novel_entities: int | None = None,
    rare_hits: int | None = None,
    unique_evidence_items: int | None = None,
    uncertainty_reduction: float | None = None,
) -> RegimeUtilityEvidence:
    """Build a regime-specific metric vector without inventing promotion weights."""
    counts = (
        raw_results,
        unique_candidates,
        qualified_candidates,
        direct_or_official_candidates,
        duplicate_results,
        excluded_results,
    )
    if any(value < 0 for value in counts):
        raise ValueError("regime_utility_counts_must_be_nonnegative")
    if unique_candidates > raw_results:
        raise ValueError("unique_candidates_exceed_raw_results")
    if qualified_candidates > unique_candidates:
        raise ValueError("qualified_candidates_exceed_unique_candidates")
    if direct_or_official_candidates > qualified_candidates:
        raise ValueError("direct_or_official_candidates_exceed_qualified_candidates")
    if duplicate_results + excluded_results > raw_results:
        raise ValueError("duplicate_and_excluded_exceed_raw_results")
    if uncertainty_reduction is not None and not 0.0 <= uncertainty_reduction <= 1.0:
        raise ValueError("uncertainty_reduction_out_of_range")

    base = {
        "qualified_per_unique": _ratio(qualified_candidates, unique_candidates),
        "direct_or_official_per_qualified": _ratio(
            direct_or_official_candidates,
            qualified_candidates,
        ),
        "unique_per_raw": _ratio(unique_candidates, raw_results),
        "duplicate_or_excluded_waste_per_raw": _ratio(
            duplicate_results + excluded_results,
            raw_results,
        ),
    }

    if regime == "precision":
        return RegimeUtilityEvidence(
            regime=regime,
            evidence_complete=True,
            reason_code="precision_vector_complete",
            metrics={
                "qualified_per_unique": base["qualified_per_unique"],
                "direct_or_official_per_qualified": base[
                    "direct_or_official_per_qualified"
                ],
                "duplicate_or_excluded_waste_per_raw": base[
                    "duplicate_or_excluded_waste_per_raw"
                ],
            },
        )

    if regime == "balanced":
        return RegimeUtilityEvidence(
            regime=regime,
            evidence_complete=True,
            reason_code="balanced_vector_complete",
            metrics=base,
        )

    discovery_values = (
        novel_entities,
        rare_hits,
        unique_evidence_items,
        uncertainty_reduction,
    )
    if any(value is None for value in discovery_values):
        return RegimeUtilityEvidence(
            regime=regime,
            evidence_complete=False,
            reason_code="discovery_evidence_incomplete",
            metrics=base,
        )
    assert novel_entities is not None
    assert rare_hits is not None
    assert unique_evidence_items is not None
    assert uncertainty_reduction is not None
    if any(value < 0 for value in (novel_entities, rare_hits, unique_evidence_items)):
        raise ValueError("discovery_utility_counts_must_be_nonnegative")
    if novel_entities > unique_candidates:
        raise ValueError("novel_entities_exceed_unique_candidates")
    if rare_hits > unique_candidates:
        raise ValueError("rare_hits_exceed_unique_candidates")

    return RegimeUtilityEvidence(
        regime=regime,
        evidence_complete=True,
        reason_code="discovery_vector_complete",
        metrics={
            **base,
            "novel_entities_per_unique": _ratio(novel_entities, unique_candidates),
            "rare_hits_per_unique": _ratio(rare_hits, unique_candidates),
            "unique_evidence_items_per_raw": _ratio(unique_evidence_items, raw_results),
            "uncertainty_reduction": round(float(uncertainty_reduction), 6),
        },
    )
