from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field

from app.search_observer_promotion import QualityGuard
from app.search_observer_scoring import ObservedMarginalYield


class QualityModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QualityMetrics(QualityModel):
    sample_count: int = Field(ge=0)
    query_count: int = Field(ge=0)
    qualified_per_query: float = Field(ge=0.0)
    direct_or_official_per_query: float = Field(ge=0.0)
    waste_ratio: float = Field(ge=0.0, le=1.0)
    latency_ms_per_query: float = Field(ge=0.0)
    cost_rub_per_query: float = Field(ge=0.0)


class QualityRegressionThresholds(QualityModel):
    """Owner/policy supplied thresholds; intentionally has no defaults."""

    max_qualified_yield_drop_ratio: float = Field(ge=0.0, le=1.0)
    max_direct_or_official_yield_drop_ratio: float = Field(ge=0.0, le=1.0)
    max_waste_ratio_increase: float = Field(ge=0.0, le=1.0)
    max_latency_increase_ratio: float = Field(ge=0.0)
    max_cost_increase_ratio: float = Field(ge=0.0)


class QualityComparison(QualityModel):
    baseline: QualityMetrics
    candidate: QualityMetrics
    thresholds: QualityRegressionThresholds | None = None
    guard: QualityGuard


def summarize_quality_metrics(outcomes: Iterable[ObservedMarginalYield]) -> QualityMetrics:
    items = list(outcomes)
    query_count = sum(item.added_queries for item in items)
    raw_results = sum(item.added_raw_results for item in items)
    qualified = sum(item.added_qualified_candidates for item in items)
    direct = sum(item.added_direct_or_official_candidates for item in items)
    duplicates = sum(item.duplicate_results for item in items)
    excluded = sum(item.excluded_results for item in items)
    latency_ms = sum(item.latency_ms for item in items)
    cost_rub = sum(item.cost_rub for item in items)

    wasted = min(raw_results, duplicates + excluded)
    return QualityMetrics(
        sample_count=len(items),
        query_count=query_count,
        qualified_per_query=round(qualified / query_count, 6) if query_count else 0.0,
        direct_or_official_per_query=round(direct / query_count, 6) if query_count else 0.0,
        waste_ratio=round(wasted / raw_results, 6) if raw_results else 0.0,
        latency_ms_per_query=round(latency_ms / query_count, 6) if query_count else 0.0,
        cost_rub_per_query=round(cost_rub / query_count, 6) if query_count else 0.0,
    )


def _relative_regressed(*, baseline: float, candidate: float, allowed_drop: float) -> bool:
    if baseline <= 0.0:
        return False
    return candidate < baseline * (1.0 - allowed_drop)


def _relative_increased(*, baseline: float, candidate: float, allowed_increase: float) -> bool:
    if baseline <= 0.0:
        return candidate > 0.0
    return candidate > baseline * (1.0 + allowed_increase)


def derive_quality_guard(
    *,
    baseline: QualityMetrics,
    candidate: QualityMetrics,
    thresholds: QualityRegressionThresholds | None,
) -> QualityComparison:
    """Compare measured quality only; never invent policy thresholds.

    Missing thresholds intentionally produce an incomplete QualityGuard, which
    keeps promotion fail-closed in `evaluate_promotion_gate`.
    """

    if thresholds is None:
        return QualityComparison(
            baseline=baseline,
            candidate=candidate,
            thresholds=None,
            guard=QualityGuard(),
        )

    guard = QualityGuard(
        qualified_yield_regressed=_relative_regressed(
            baseline=baseline.qualified_per_query,
            candidate=candidate.qualified_per_query,
            allowed_drop=thresholds.max_qualified_yield_drop_ratio,
        ),
        direct_or_official_yield_regressed=_relative_regressed(
            baseline=baseline.direct_or_official_per_query,
            candidate=candidate.direct_or_official_per_query,
            allowed_drop=thresholds.max_direct_or_official_yield_drop_ratio,
        ),
        duplicate_or_excluded_waste_regressed=(
            candidate.waste_ratio
            > baseline.waste_ratio + thresholds.max_waste_ratio_increase
        ),
        latency_or_cost_outside_policy=(
            _relative_increased(
                baseline=baseline.latency_ms_per_query,
                candidate=candidate.latency_ms_per_query,
                allowed_increase=thresholds.max_latency_increase_ratio,
            )
            or _relative_increased(
                baseline=baseline.cost_rub_per_query,
                candidate=candidate.cost_rub_per_query,
                allowed_increase=thresholds.max_cost_increase_ratio,
            )
        ),
    )
    return QualityComparison(
        baseline=baseline,
        candidate=candidate,
        thresholds=thresholds,
        guard=guard,
    )
