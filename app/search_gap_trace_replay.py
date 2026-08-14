from __future__ import annotations

from collections import defaultdict
from urllib.parse import urlparse

from app.search_gap_query_replay import GapQueryReplayCase, ReplaySearchResult
from app.search_gap_shadow_refinement import GapCode
from app.search_regime_utility import SearchRegime
from app.trace_ledger import TraceEvent


QUALITY_SENSITIVE_GAPS = frozenset(
    {
        "no_returned_candidates",
        "region_confirmation_missing",
        "industry_confirmation_missing",
    }
)
SUPPORTED_TRACE_REPLAY_GAPS = frozenset({"sparse_yield", *QUALITY_SENSITIVE_GAPS})


def _canonical_query(value: str) -> str:
    return " ".join(value.split()).strip().casefold()


def _domain(value: str) -> str:
    return (urlparse(value).hostname or "").casefold().removeprefix("www.")


def replay_case_from_trace(
    events: list[TraceEvent],
    *,
    gap_code: GapCode,
    effective_regime: SearchRegime,
    suggested_follow_up_query: str,
    baseline_domains: list[str] | None = None,
) -> GapQueryReplayCase | None:
    """Build one exact-query offline replay case from retained trace evidence.

    This function is intentionally fail-closed. It never performs a search and it
    refuses gaps that the current trace corpus cannot prove. Quality-sensitive
    replay also requires unambiguous query lineage for every candidate-quality
    fact used by the selected query.
    """
    if gap_code not in SUPPORTED_TRACE_REPLAY_GAPS:
        return None
    if not events:
        return None

    mission_ids = {event.mission_id for event in events}
    attempt_ids = {event.attempt_id for event in events}
    if len(mission_ids) != 1 or len(attempt_ids) != 1:
        raise ValueError("trace_replay_requires_single_attempt")

    wanted = _canonical_query(suggested_follow_up_query)
    planned = [
        event
        for event in events
        if event.component == "search_gateway"
        and event.operation == "query_planned"
        and _canonical_query(str(event.metadata.get("query_text") or "")) == wanted
    ]
    if len(planned) != 1:
        return None

    query_index = planned[0].metadata.get("query_index")
    if not isinstance(query_index, int):
        return None

    result_events = [
        event
        for event in events
        if event.component == "search_gateway"
        and event.operation == "result_item"
        and event.metadata.get("query_index") == query_index
    ]
    if not result_events:
        return None

    domain_query_indexes: dict[str, set[int]] = defaultdict(set)
    for event in events:
        if event.component != "search_gateway" or event.operation != "result_item":
            continue
        result_url = str(event.metadata.get("result_url") or "")
        domain = _domain(result_url)
        index = event.metadata.get("query_index")
        if domain and isinstance(index, int):
            domain_query_indexes[domain].add(index)

    candidate_by_domain: dict[str, TraceEvent] = {}
    excluded_domains: set[str] = set()
    for event in events:
        if event.component != "hunter":
            continue
        candidate_url = str(event.metadata.get("candidate_url") or "")
        domain = _domain(candidate_url)
        if not domain:
            continue
        if event.operation in {"candidate_returned", "candidate_output_omitted"}:
            candidate_by_domain[domain] = event
        elif event.operation == "candidate_excluded":
            excluded_domains.add(domain)

    if gap_code in QUALITY_SENSITIVE_GAPS:
        for event in result_events:
            domain = _domain(str(event.metadata.get("result_url") or ""))
            if domain in candidate_by_domain and len(domain_query_indexes.get(domain, set())) != 1:
                return None

    results: list[ReplaySearchResult] = []
    for event in result_events:
        result_url = str(event.metadata.get("result_url") or "")
        if not result_url:
            continue
        domain = _domain(result_url)
        candidate = candidate_by_domain.get(domain)
        qualified = candidate is not None
        source_role = str(candidate.metadata.get("source_role") or "") if candidate else ""
        region_value = candidate.metadata.get("region_confirmed") if candidate else None
        industry_value = candidate.metadata.get("industry_match") if candidate else None
        results.append(
            ReplaySearchResult(
                url=result_url,
                qualified=qualified,
                direct_or_official=qualified and source_role == "direct_candidate",
                excluded=domain in excluded_domains,
                region_confirmed=region_value is True,
                industry_confirmed=isinstance(industry_value, (int, float)) and industry_value > 0,
                novel_entity=None,
                rare_hit=None,
            )
        )

    if not results:
        return None

    return GapQueryReplayCase(
        mission_id=events[0].mission_id,
        attempt_id=events[0].attempt_id,
        gap_code=gap_code,
        effective_regime=effective_regime,
        suggested_follow_up_query=suggested_follow_up_query,
        observed_query=str(planned[0].metadata.get("query_text") or ""),
        baseline_domains=baseline_domains or [],
        results=results,
        routing_changed=False,
    )
