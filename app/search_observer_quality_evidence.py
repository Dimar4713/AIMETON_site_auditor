from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.search_observer_llm import ObserverAction
from app.search_observer_quality import QualityMetrics, summarize_quality_metrics
from app.search_observer_scoring import (
    ObservedMarginalYield,
    SecondWaveShadowAction,
    assess_second_wave_shadow,
)


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


class ShadowSecondWaveActionProfile(QualityEvidenceModel):
    """Zero-cost hindsight profile derived only from stored marginal outcomes."""

    evidence_kind: str = "shadow_second_wave_action_profile"
    promotion_eligible: bool = False
    sample_count: int = Field(ge=1)
    continue_count: int = Field(ge=0)
    refine_count: int = Field(ge=0)
    skip_count: int = Field(ge=0)
    high_waste_count: int = Field(ge=0)
    quality_gain_count: int = Field(ge=0)
    mean_waste_ratio: float = Field(ge=0.0, le=1.0)
    routing_changed: bool = False
    reason_code: str = "shadow_profile_not_steering_candidate"


class ShadowObserverCalibrationProfile(QualityEvidenceModel):
    """Offline comparison of stored Observer advice with hindsight treatment."""

    evidence_kind: str = "shadow_observer_calibration_profile"
    promotion_eligible: bool = False
    sample_count: int = Field(ge=1)
    aligned_count: int = Field(ge=0)
    disagreement_count: int = Field(ge=0)
    disagreement_ratio: float = Field(ge=0.0, le=1.0)
    over_refine_count: int = Field(ge=0)
    under_refine_count: int = Field(ge=0)
    continued_without_gain_count: int = Field(ge=0)
    other_disagreement_count: int = Field(ge=0)
    routing_changed: bool = False
    reason_code: str = "shadow_calibration_not_steering_candidate"


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


def _stored_marginal_outcomes(payload: Mapping[str, Any]) -> list[ObservedMarginalYield]:
    marginals: list[ObservedMarginalYield] = []
    for scenario in payload.get("scenarios", []):
        for outcome in scenario.get("outcomes", []):
            score = outcome.get("score") or {}
            if score.get("routing_changed") is True:
                raise ValueError("shadow_action_profile_requires_routing_unchanged")
            marginal = score.get("outcome")
            if marginal is not None:
                marginals.append(ObservedMarginalYield.model_validate(marginal))
    return marginals


def load_shadow_quality_proxy(payload: Mapping[str, Any]) -> ShadowQualityProxy:
    """Recover source/later/marginal metrics from heterogeneous shadow evidence."""
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


def load_shadow_second_wave_action_profile(
    payload: Mapping[str, Any],
) -> ShadowSecondWaveActionProfile:
    """Classify stored marginal outcomes without calling providers or steering routing."""
    marginals = _stored_marginal_outcomes(payload)
    if not marginals:
        raise ValueError("shadow_action_profile_requires_marginal_evidence")
    decisions = [assess_second_wave_shadow(item) for item in marginals]
    counts = Counter(item.preferred_action for item in decisions)
    return ShadowSecondWaveActionProfile(
        sample_count=len(decisions),
        continue_count=counts[SecondWaveShadowAction.CONTINUE],
        refine_count=counts[SecondWaveShadowAction.REFINE],
        skip_count=counts[SecondWaveShadowAction.SKIP],
        high_waste_count=sum(item.high_waste for item in decisions),
        quality_gain_count=sum(item.quality_gain_observed for item in decisions),
        mean_waste_ratio=round(sum(item.waste_ratio for item in decisions) / len(decisions), 6),
        routing_changed=False,
    )


def _observer_treatment(action: ObserverAction) -> SecondWaveShadowAction | None:
    if action in {ObserverAction.CONTINUE, ObserverAction.BOOST}:
        return SecondWaveShadowAction.CONTINUE
    if action in {ObserverAction.REFINE, ObserverAction.SLOW}:
        return SecondWaveShadowAction.REFINE
    if action == ObserverAction.STOP:
        return SecondWaveShadowAction.SKIP
    return None


def load_shadow_observer_calibration_profile(
    payloads: Mapping[str, Any] | Iterable[Mapping[str, Any]],
) -> ShadowObserverCalibrationProfile:
    """Compare stored advisory actions to hindsight treatment, with zero live calls."""
    batches = (payloads,) if isinstance(payloads, Mapping) else tuple(payloads)
    pairs: list[tuple[SecondWaveShadowAction, SecondWaveShadowAction]] = []
    for payload in batches:
        for scenario in payload.get("scenarios", []):
            for outcome in scenario.get("outcomes", []):
                score = outcome.get("score") or {}
                if score.get("routing_changed") is True:
                    raise ValueError("shadow_calibration_requires_routing_unchanged")
                marginal = score.get("outcome")
                raw_action = score.get("action")
                if marginal is None or raw_action is None:
                    continue
                observer = _observer_treatment(ObserverAction(raw_action))
                if observer is None:
                    continue
                hindsight = assess_second_wave_shadow(
                    ObservedMarginalYield.model_validate(marginal)
                ).preferred_action
                pairs.append((observer, hindsight))
    if not pairs:
        raise ValueError("shadow_calibration_requires_comparable_evidence")

    aligned = sum(observer == hindsight for observer, hindsight in pairs)
    over_refine = sum(
        observer == SecondWaveShadowAction.REFINE
        and hindsight == SecondWaveShadowAction.CONTINUE
        for observer, hindsight in pairs
    )
    under_refine = sum(
        observer == SecondWaveShadowAction.CONTINUE
        and hindsight == SecondWaveShadowAction.REFINE
        for observer, hindsight in pairs
    )
    continued_without_gain = sum(
        observer == SecondWaveShadowAction.CONTINUE
        and hindsight == SecondWaveShadowAction.SKIP
        for observer, hindsight in pairs
    )
    disagreement = len(pairs) - aligned
    categorized = over_refine + under_refine + continued_without_gain
    return ShadowObserverCalibrationProfile(
        sample_count=len(pairs),
        aligned_count=aligned,
        disagreement_count=disagreement,
        disagreement_ratio=round(disagreement / len(pairs), 6),
        over_refine_count=over_refine,
        under_refine_count=under_refine,
        continued_without_gain_count=continued_without_gain,
        other_disagreement_count=disagreement - categorized,
        routing_changed=False,
    )
