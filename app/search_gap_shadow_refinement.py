from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.models import HuntCandidate, HuntFunnel, HuntRequest
from app.search_regime_utility import SearchRegime

GapCode = Literal[
    "sparse_yield",
    "duplicate_or_excluded_pressure",
    "no_returned_candidates",
    "region_confirmation_missing",
    "industry_confirmation_missing",
    "discovery_novelty_unmeasured",
]


@dataclass(frozen=True)
class SearchGapObservation:
    code: GapCode
    evidence_target: str
    reason: str


@dataclass(frozen=True)
class FollowUpQuerySuggestion:
    query: str
    reason_code: GapCode
    evidence_target: str
    routing_changed: bool = False
    steering_enabled: bool = False


@dataclass(frozen=True)
class ShadowRefinementPlan:
    gaps: tuple[SearchGapObservation, ...]
    suggestions: tuple[FollowUpQuerySuggestion, ...]
    routing_changed: bool = False
    steering_enabled: bool = False


def _normalize_query(value: str) -> str:
    return " ".join(value.split()).strip()


def _subjects(req: HuntRequest) -> list[str]:
    raw = [*req.industries, *req.focus]
    result: list[str] = []
    seen: set[str] = set()
    for value in raw:
        normalized = _normalize_query(value)
        key = normalized.casefold()
        if normalized and key not in seen:
            seen.add(key)
            result.append(normalized)
    return result or ["компания"]


def observe_search_gaps(
    *,
    funnel: HuntFunnel,
    effective_regime: SearchRegime,
    candidates: list[HuntCandidate],
) -> list[SearchGapObservation]:
    gaps: list[SearchGapObservation] = []
    if funnel.raw_results <= 0 or funnel.unique_candidates <= 2 or funnel.qualified_candidates <= 1:
        gaps.append(SearchGapObservation(
            code="sparse_yield",
            evidence_target="more_unique_candidates",
            reason="wave_1 produced too little unique or qualified yield",
        ))

    if funnel.raw_results > 0:
        waste_ratio = (funnel.duplicate_results + funnel.excluded_results) / funnel.raw_results
        if waste_ratio >= 0.45:
            gaps.append(SearchGapObservation(
                code="duplicate_or_excluded_pressure",
                evidence_target="diverse_unique_domains",
                reason="duplicate and excluded results consume at least 45% of raw yield",
            ))

    if funnel.raw_results > 0 and funnel.returned_candidates == 0:
        gaps.append(SearchGapObservation(
            code="no_returned_candidates",
            evidence_target="returnable_direct_candidates",
            reason="search produced raw results but no candidate reached the response",
        ))

    candidate_window_complete = (
        funnel.qualified_candidates == funnel.returned_candidates == len(candidates)
    )
    if (
        candidate_window_complete
        and candidates
        and not any(candidate.region_confirmed is True for candidate in candidates)
    ):
        gaps.append(SearchGapObservation(
            code="region_confirmation_missing",
            evidence_target="explicit_region_evidence",
            reason="complete retained candidate window has no confirmed regional evidence",
        ))

    industry_signals = [
        candidate.pre_score_factors.get("industry_match")
        for candidate in candidates
        if "industry_match" in candidate.pre_score_factors
    ]
    if (
        candidate_window_complete
        and candidates
        and industry_signals
        and not any(value for value in industry_signals)
    ):
        gaps.append(SearchGapObservation(
            code="industry_confirmation_missing",
            evidence_target="explicit_industry_evidence",
            reason="complete retained candidate window has no positive industry-match signal",
        ))

    if effective_regime == "discovery":
        gaps.append(SearchGapObservation(
            code="discovery_novelty_unmeasured",
            evidence_target="novel_or_rare_entities",
            reason="discovery mode requires explicit novelty/rare-hit evidence",
        ))
    return gaps


def build_shadow_follow_up_queries(
    *,
    req: HuntRequest,
    funnel: HuntFunnel,
    executed_queries: list[str],
    effective_regime: SearchRegime,
    candidates: list[HuntCandidate],
    max_suggestions: int = 6,
) -> ShadowRefinementPlan:
    """Build bounded post-wave query suggestions without executing search or calling an LLM."""
    gaps = observe_search_gaps(
        funnel=funnel,
        effective_regime=effective_regime,
        candidates=candidates,
    )
    if max_suggestions <= 0:
        return ShadowRefinementPlan(gaps=tuple(gaps), suggestions=())

    executed = {_normalize_query(query).casefold() for query in executed_queries}
    emitted: set[str] = set()
    suggestions: list[FollowUpQuerySuggestion] = []
    subjects = _subjects(req)

    suffixes: dict[GapCode, tuple[str, ...]] = {
        "sparse_yield": ("контакты", "услуги"),
        "duplicate_or_excluded_pressure": ("адрес телефон", "официальный сайт контакты"),
        "no_returned_candidates": ("сайт услуги", "контакты организация"),
        "region_confirmation_missing": ("адрес", "филиал"),
        "industry_confirmation_missing": ("услуги", "прайс"),
        "discovery_novelty_unmeasured": ("каталог организаций", "ассоциация участники"),
    }

    for gap in gaps:
        for subject in subjects:
            for suffix in suffixes[gap.code]:
                query = _normalize_query(f"{subject} {req.region} {suffix}")
                key = query.casefold()
                if key in executed or key in emitted:
                    continue
                emitted.add(key)
                suggestions.append(FollowUpQuerySuggestion(
                    query=query,
                    reason_code=gap.code,
                    evidence_target=gap.evidence_target,
                ))
                if len(suggestions) >= max_suggestions:
                    return ShadowRefinementPlan(
                        gaps=tuple(gaps),
                        suggestions=tuple(suggestions),
                    )
    return ShadowRefinementPlan(gaps=tuple(gaps), suggestions=tuple(suggestions))
