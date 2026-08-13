from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SearchRegime = Literal["precision", "balanced", "discovery"]


@dataclass(frozen=True)
class SearchRegimeDecision:
    effective: SearchRegime
    reason: str
    routing_changed: bool = False
    steering_enabled: bool = False


def resolve_auto_search_regime(
    *,
    raw_results: int,
    unique_candidates: int,
    qualified_candidates: int,
    duplicate_results: int,
    excluded_results: int,
) -> SearchRegimeDecision:
    """Resolve an advisory regime from an observed Hunter funnel without steering."""
    if raw_results <= 0 or unique_candidates <= 2 or qualified_candidates <= 1:
        return SearchRegimeDecision("discovery", "rarity_or_sparsity")

    waste = duplicate_results + excluded_results
    waste_ratio = waste / raw_results if raw_results else 0.0
    qualified_ratio = qualified_candidates / unique_candidates if unique_candidates else 0.0

    if waste_ratio >= 0.45:
        return SearchRegimeDecision("precision", "duplicate_or_excluded_pressure")
    if qualified_candidates >= 10 and qualified_ratio >= 0.6:
        return SearchRegimeDecision("precision", "sufficient_high_quality_candidates")
    return SearchRegimeDecision("balanced", "balanced_default")
