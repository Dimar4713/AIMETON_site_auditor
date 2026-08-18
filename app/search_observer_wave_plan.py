from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class WavePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_wave_queries: list[str]
    reserve_queries: list[str]
    total_query_budget: int = Field(ge=0)
    reserve_query_budget: int = Field(ge=0)
    steering_enabled: bool
    reason_code: str


def plan_bounded_search_waves(
    queries: list[str],
    *,
    steering_enabled: bool,
    requested_reserve_queries: int,
) -> WavePlan:
    """Split an already-bounded query plan without increasing its total size.

    With steering disabled the output is exactly the legacy one-wave plan. When
    enabled, a bounded tail of the existing plan is held for an optional second
    wave. This function never generates extra queries and never calls providers.
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
    # Always leave at least one query in the first wave and never reserve more
    # than half of the bounded plan in this first Phase-D implementation.
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
