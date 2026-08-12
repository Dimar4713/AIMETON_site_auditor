from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.search_observer_scoring import ObservedMarginalYield


class MultiWaveModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WaveOutcomeSnapshot(MultiWaveModel):
    """Cumulative, stored observation for one bounded search wave.

    This is evidence only. It cannot execute searches, call providers, or change
    routing. `wave_index` must increase for causal marginal-yield comparison.
    """

    mission_id: str = Field(min_length=1, max_length=120)
    attempt_id: str = Field(min_length=1, max_length=120)
    wave_index: int = Field(ge=1)
    query_count: int = Field(ge=0)
    raw_results: int = Field(ge=0)
    unique_domains: int = Field(ge=0)
    qualified_candidates: int = Field(ge=0)
    direct_or_official_candidates: int = Field(ge=0)
    duplicate_results: int = Field(ge=0)
    excluded_results: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    cost_rub: float = Field(ge=0.0)
    routing_changed: bool = False


def derive_later_marginal_yield(
    earlier: WaveOutcomeSnapshot,
    later: WaveOutcomeSnapshot,
) -> ObservedMarginalYield:
    """Derive a strictly-later marginal yield from two stored snapshots.

    The function is deliberately strict: same-wave comparisons, identity
    mismatches, routing changes, and any negative cumulative delta are rejected
    instead of being normalized. This prevents same-wave funnel data from being
    misrepresented as causal evidence for an Observer recommendation.
    """
    if earlier.mission_id != later.mission_id or earlier.attempt_id != later.attempt_id:
        raise ValueError("multiwave_identity_mismatch")
    if later.wave_index <= earlier.wave_index:
        raise ValueError("later_wave_required")
    if earlier.routing_changed or later.routing_changed:
        raise ValueError("multiwave_scoring_requires_routing_unchanged")

    fields = {
        "added_queries": later.query_count - earlier.query_count,
        "added_raw_results": later.raw_results - earlier.raw_results,
        "added_unique_domains": later.unique_domains - earlier.unique_domains,
        "added_qualified_candidates": later.qualified_candidates - earlier.qualified_candidates,
        "added_direct_or_official_candidates": (
            later.direct_or_official_candidates - earlier.direct_or_official_candidates
        ),
        "duplicate_results": later.duplicate_results - earlier.duplicate_results,
        "excluded_results": later.excluded_results - earlier.excluded_results,
        "latency_ms": later.latency_ms - earlier.latency_ms,
        "cost_rub": round(later.cost_rub - earlier.cost_rub, 6),
    }
    if any(value < 0 for value in fields.values()):
        raise ValueError("multiwave_cumulative_counter_regression")
    return ObservedMarginalYield(**fields)
