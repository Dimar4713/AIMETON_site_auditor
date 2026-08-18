from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.search_gateway import SearchResponse
from app.search_observer import SearchWaveTelemetry, build_search_wave_telemetry
from app.search_observer_llm import SearchObserverRecommendation
from app.search_observer_steering import BoundedSteeringDecision, validate_bounded_continuation_steering
from app.search_observer_verified_promotion import ContinuationPromotionPermit
from app.search_observer_wave_plan import (
    WavePlan,
    assign_reserve_queries_to_directions,
    plan_bounded_search_waves,
    prioritize_reserve_queries,
)

SearchMany = Callable[[list[str]], Awaitable[list[SearchResponse]]]
ObserveWave = Callable[[SearchWaveTelemetry], Awaitable[SearchObserverRecommendation | None]]


@dataclass(frozen=True)
class BoundedContinuationRuntimeResult:
    executed_queries: list[str]
    responses: list[SearchResponse]
    first_wave_telemetry: SearchWaveTelemetry
    wave_plan: WavePlan
    observer_recommendation: SearchObserverRecommendation | None
    steering_decision: BoundedSteeringDecision | None
    reserve_reordered: bool


async def run_bounded_continuation_search(
    queries: list[str],
    *,
    enabled: bool,
    requested_search_regime: str,
    requested_reserve_queries: int,
    permit: ContinuationPromotionPermit | None,
    search_many: SearchMany,
    observe_wave: ObserveWave,
) -> BoundedContinuationRuntimeResult:
    """Run the first reversible Search Observer steering envelope.

    Disabled/auto mode executes the complete legacy query list in one wave.
    Explicit-regime enabled mode holds a bounded tail, observes wave 1, and may
    prioritize reserve queries associated with continuation-qualified directions.
    Every planned reserve query is still executed: this phase cannot suppress
    coverage, add queries, change provider authority, or spend beyond the original
    bounded query plan. The Observer is evaluated at most once per hunt here.
    """
    regime_is_explicit = requested_search_regime in {"precision", "balanced", "discovery"}
    wave_plan = plan_bounded_search_waves(
        queries,
        steering_enabled=enabled and regime_is_explicit,
        requested_reserve_queries=requested_reserve_queries,
    )

    if not wave_plan.steering_enabled:
        responses = await search_many(wave_plan.first_wave_queries)
        telemetry = build_search_wave_telemetry(wave_plan.first_wave_queries, responses)
        return BoundedContinuationRuntimeResult(
            executed_queries=list(wave_plan.first_wave_queries),
            responses=responses,
            first_wave_telemetry=telemetry,
            wave_plan=wave_plan,
            observer_recommendation=None,
            steering_decision=None,
            reserve_reordered=False,
        )

    first_responses = await search_many(wave_plan.first_wave_queries)
    telemetry = build_search_wave_telemetry(wave_plan.first_wave_queries, first_responses)
    recommendation = await observe_wave(telemetry)

    decision = validate_bounded_continuation_steering(
        [] if recommendation is None else recommendation.recommendations,
        enabled=True,
        permit=permit,
        remaining_query_budget=wave_plan.reserve_query_budget,
        effective_regime=requested_search_regime,
        direction_count=len(wave_plan.first_wave_queries),
    )

    assignments = assign_reserve_queries_to_directions(
        wave_plan.first_wave_queries,
        wave_plan.reserve_queries,
    )
    reserve_queries = list(wave_plan.reserve_queries)
    if decision.accepted_direction_indexes:
        reserve_queries = prioritize_reserve_queries(
            assignments,
            accepted_direction_indexes=decision.accepted_direction_indexes,
        )

    reserve_responses = await search_many(reserve_queries)
    executed_queries = list(wave_plan.first_wave_queries) + reserve_queries
    return BoundedContinuationRuntimeResult(
        executed_queries=executed_queries,
        responses=first_responses + reserve_responses,
        first_wave_telemetry=telemetry,
        wave_plan=wave_plan,
        observer_recommendation=recommendation,
        steering_decision=decision,
        reserve_reordered=reserve_queries != wave_plan.reserve_queries,
    )
