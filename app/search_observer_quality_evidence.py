from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.search_observer_quality import QualityMetrics, summarize_quality_metrics
from app.search_observer_scoring import ObservedMarginalYield


class QualityEvidenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SnapshotCounters(QualityEvidenceModel):
    model_config = ConfigDict(extra="ignore")

    query_count: int = Field(ge=0)
    raw_results: int = Field(ge=0)
    qualified_candidates: int = Field(ge=0)
    direct_or_official_candidates: int = Field(ge=0)
    duplicate_results: int = Field(ge=0)
    excluded_results: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    cost_rub: float = Field(ge=0.0)


class ShadowQualityProxy(QualityEvidenceModel):
    evidence_kind: str = "shadow_proxy"
    promotion_eligible: bool = False
    source: QualityMetrics
    later: QualityMetrics
    marginal: QualityMetrics
    reason_code: str = "shadow_proxy_not_steering_candidate"


def _summarize_snapshots(items: Iterable[SnapshotCounters]) -> QualityMetrics:
    snapshots = list(items)
    query_count = sum(item.query_count for item in snapshots)
    raw_results = sum(item.raw_results for item in snapshots)
    qualified = sum(item.qualified_candidates for item in snapshots)
    direct = sum(item.direct_or_official_candidates for item in snapshots)
    duplicates = sum(item.duplicate_results for item in snapshots)
    excluded = sum(item.excluded_results for item in snapshots)
    latency_ms = sum(item.latency_ms for item in snapshots)
    cost_rub = sum(item.cost_rub for item in snapshots)
    wasted = min(raw_results, duplicates + excluded)
    return QualityMetrics(
        sample_count=len(snapshots),
        query_count=query_count,
        qualified_per_query=round(qualified / query_count, 6) if query_count else 0.0,
        direct_or_official_per_query=round(direct / query_count, 6) if query_count else 0.0,
        waste_ratio=round(wasted / raw_results, 6) if raw_results else 0.0,
        latency_ms_per_query=round(latency_ms / query_count, 6) if query_count else 0.0,
        cost_rub_per_query=round(cost_rub / query_count, 6) if query_count else 0.0,
    )


def load_shadow_quality_proxy(payload: Mapping[str, Any]) -> ShadowQualityProxy:
    """Recover source/later/marginal metrics from heterogeneous shadow evidence.

    These measurements are useful for offline diagnostics but are explicitly not
    a steering candidate and therefore cannot satisfy the promotion quality gate.
    """
    sources: list[SnapshotCounters] = []
    laters: list[SnapshotCounters] = []
    marginals: list[ObservedMarginalYield] = []
    for scenario in payload.get("scenarios", []):
        for outcome in scenario.get("outcomes", []):
            source = outcome.get("source_snapshot")
            later = outcome.get("later_snapshot")
            score = outcome.get("score") or {}
            marginal = score.get("outcome")
            if source is not None:
                sources.append(SnapshotCounters.model_validate(source))
            if later is not None:
                laters.append(SnapshotCounters.model_validate(later))
            if marginal is not None:
                marginals.append(ObservedMarginalYield.model_validate(marginal))
    if not sources or not laters or not marginals:
        raise ValueError("shadow_quality_proxy_requires_source_later_and_marginal_evidence")
    return ShadowQualityProxy(
        source=_summarize_snapshots(sources),
        later=_summarize_snapshots(laters),
        marginal=summarize_quality_metrics(marginals),
    )
