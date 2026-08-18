from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field


class WavePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_wave_queries: list[str]
    reserve_queries: list[str]
    total_query_budget: int = Field(ge=0)
    reserve_query_budget: int = Field(ge=0)
    steering_enabled: bool
    reason_code: str


class AssignedReserveQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    direction_index: int = Field(ge=0)
    lexical_overlap: float = Field(ge=0.0, le=1.0)


def _query_tokens(query: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[\w-]+", query.casefold(), flags=re.UNICODE)
        if len(token) >= 3
    }


def _overlap(left: str, right: str) -> float:
    a = _query_tokens(left)
    b = _query_tokens(right)
    if not a or not b:
        return 0.0
    return round(len(a & b) / len(a | b), 6)


def assign_reserve_queries_to_directions(
    first_wave_queries: list[str],
    reserve_queries: list[str],
) -> list[AssignedReserveQuery]:
    """Deterministically associate reserved variants with observed directions.

    Association is lexical and has no routing authority. Ties keep the earliest
    first-wave direction, making replay deterministic. The mapping lets bounded
    continuation steering prioritize already-planned variants without generating
    new queries or increasing the query budget.
    """
    if not first_wave_queries:
        return []

    assignments: list[AssignedReserveQuery] = []
    for query in reserve_queries:
        scored = [(_overlap(query, candidate), index) for index, candidate in enumerate(first_wave_queries)]
        score, index = max(scored, key=lambda item: (item[0], -item[1]))
        assignments.append(
            AssignedReserveQuery(
                query=query,
                direction_index=index,
                lexical_overlap=score,
            )
        )
    return assignments


def prioritize_reserve_queries(
    assignments: list[AssignedReserveQuery],
    *,
    accepted_direction_indexes: list[int],
) -> list[str]:
    """Move continuation-qualified reserve work first without dropping fallback work."""
    accepted = set(accepted_direction_indexes)
    priority = [item.query for item in assignments if item.direction_index in accepted]
    fallback = [item.query for item in assignments if item.direction_index not in accepted]
    return priority + fallback


def plan_bounded_search_waves(
    queries: list[str],
    *,
    steering_enabled: bool,
    requested_reserve_queries: int,
) -> WavePlan:
    """Split an already-bounded query plan without increasing its total size.

    With steering disabled the output is exactly the legacy one-wave plan. When
    enabled, a bounded tail of the existing plan is held for a second wave. No
    query is generated or deleted here; runtime fail-open can still execute every
    reserved query if Observer evidence is missing or rejected.
    """
    normalized: list[str] = []
    seen: set[str] = set()
    for query in queries:
        value = " ".join(str(query).split()).strip()
        key = value.casefold()
        if not value or key in seen:
            continue
        seen.add(key)
        normalized.append(value)

    total = len(normalized)
    if not steering_enabled or total < 2:
        return WavePlan(
            first_wave_queries=normalized,
            reserve_queries=[],
            total_query_budget=total,
            reserve_query_budget=0,
            steering_enabled=False,
            reason_code="legacy_single_wave",
        )

    requested = max(0, int(requested_reserve_queries))
    reserve_count = min(requested, total // 2, total - 1)
    if reserve_count <= 0:
        return WavePlan(
            first_wave_queries=normalized,
            reserve_queries=[],
            total_query_budget=total,
            reserve_query_budget=0,
            steering_enabled=False,
            reason_code="reserve_not_configured",
        )

    split_at = total - reserve_count
    return WavePlan(
        first_wave_queries=normalized[:split_at],
        reserve_queries=normalized[split_at:],
        total_query_budget=total,
        reserve_query_budget=reserve_count,
        steering_enabled=True,
        reason_code="bounded_reserve_planned",
    )
