from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import hashlib
from typing import Literal

from app.trace_ledger import TraceEvent


TraceMatchKind = Literal[
    "same_attempt_causal_candidate",
    "historical_noncausal_candidate",
    "same_attempt_prior_collision",
]


@dataclass(frozen=True)
class ShadowQueryMatch:
    suggestion_mission_id: str
    suggestion_attempt_id: str
    suggestion_sequence: int
    gap_code: str
    effective_regime: str
    query_digest: str
    matched_mission_id: str
    matched_attempt_id: str
    matched_sequence: int
    query_index: int
    kind: TraceMatchKind


def _canonical_query(value: str) -> str:
    return " ".join(value.split()).strip().casefold()


def _query_digest(value: str) -> str:
    return hashlib.sha256(_canonical_query(value).encode("utf-8")).hexdigest()[:16]


def find_shadow_query_matches(events: list[TraceEvent]) -> list[ShadowQueryMatch]:
    suggestions: list[tuple[TraceEvent, str]] = []
    planned: list[tuple[TraceEvent, str]] = []
    for event in events:
        if (
            event.component == "search_refinement_shadow"
            and event.operation == "follow_up_query_suggested"
        ):
            query = _canonical_query(str(event.metadata.get("query_text") or ""))
            if query:
                suggestions.append((event, query))
        elif event.component == "search_gateway" and event.operation == "query_planned":
            query = _canonical_query(str(event.metadata.get("query_text") or ""))
            if query:
                planned.append((event, query))

    matches: list[ShadowQueryMatch] = []
    for suggestion, query in suggestions:
        for query_event, planned_query in planned:
            if planned_query != query:
                continue
            query_index = query_event.metadata.get("query_index")
            if not isinstance(query_index, int):
                continue
            same_attempt = (
                suggestion.mission_id == query_event.mission_id
                and suggestion.attempt_id == query_event.attempt_id
            )
            if same_attempt and query_event.sequence > suggestion.sequence:
                kind: TraceMatchKind = "same_attempt_causal_candidate"
            elif same_attempt:
                kind = "same_attempt_prior_collision"
            else:
                kind = "historical_noncausal_candidate"
            matches.append(
                ShadowQueryMatch(
                    suggestion_mission_id=suggestion.mission_id,
                    suggestion_attempt_id=suggestion.attempt_id,
                    suggestion_sequence=suggestion.sequence,
                    gap_code=str(suggestion.metadata.get("gap_code") or suggestion.reason_code),
                    effective_regime=str(suggestion.metadata.get("effective_regime") or "unknown"),
                    query_digest=_query_digest(query),
                    matched_mission_id=query_event.mission_id,
                    matched_attempt_id=query_event.attempt_id,
                    matched_sequence=query_event.sequence,
                    query_index=query_index,
                    kind=kind,
                )
            )
    return matches


def build_shadow_query_match_summary(events: list[TraceEvent]) -> dict[str, object]:
    suggestions = [
        event
        for event in events
        if event.component == "search_refinement_shadow"
        and event.operation == "follow_up_query_suggested"
        and _canonical_query(str(event.metadata.get("query_text") or ""))
    ]
    matches = find_shadow_query_matches(events)
    usable_by_suggestion: set[tuple[str, str, int]] = set()
    buckets: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "suggestions": 0,
            "same_attempt_causal_candidates": 0,
            "historical_noncausal_candidates": 0,
            "same_attempt_prior_collisions": 0,
        }
    )

    for suggestion in suggestions:
        gap = str(suggestion.metadata.get("gap_code") or suggestion.reason_code)
        regime = str(suggestion.metadata.get("effective_regime") or "unknown")
        buckets[f"{regime}:{gap}"]["suggestions"] += 1

    for match in matches:
        key = f"{match.effective_regime}:{match.gap_code}"
        identity = (
            match.suggestion_mission_id,
            match.suggestion_attempt_id,
            match.suggestion_sequence,
        )
        if match.kind == "same_attempt_causal_candidate":
            buckets[key]["same_attempt_causal_candidates"] += 1
            usable_by_suggestion.add(identity)
        elif match.kind == "historical_noncausal_candidate":
            buckets[key]["historical_noncausal_candidates"] += 1
            usable_by_suggestion.add(identity)
        else:
            buckets[key]["same_attempt_prior_collisions"] += 1

    return {
        "evidence_kind": "search_gap_shadow_query_match_inventory",
        "suggestion_count": len(suggestions),
        "matched_suggestion_count": len(usable_by_suggestion),
        "unmatched_suggestion_count": max(0, len(suggestions) - len(usable_by_suggestion)),
        "same_attempt_causal_candidate_count": sum(
            match.kind == "same_attempt_causal_candidate" for match in matches
        ),
        "historical_noncausal_candidate_count": sum(
            match.kind == "historical_noncausal_candidate" for match in matches
        ),
        "same_attempt_prior_collision_count": sum(
            match.kind == "same_attempt_prior_collision" for match in matches
        ),
        "buckets": dict(sorted(buckets.items())),
        "routing_changed": False,
        "steering_enabled": False,
        "promotion_activated": False,
    }
