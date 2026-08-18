import pytest

from app.search_gateway import GatewayState, SearchDiagnostics, SearchResponse
from app.search_observer_llm import (
    DirectionRecommendation,
    ObserverAction,
    SearchObserverRecommendation,
)
from app.search_observer_runtime_steering import run_bounded_continuation_search
from app.search_observer_verified_promotion import verified_continuation_promotion_permit


def _response() -> SearchResponse:
    return SearchResponse(
        results=[],
        diagnostics=SearchDiagnostics(state=GatewayState.SUCCESS),
    )


@pytest.mark.asyncio
async def test_disabled_mode_is_one_legacy_search_wave_and_never_calls_observer():
    calls: list[list[str]] = []
    observer_calls = 0

    async def search_many(queries: list[str]) -> list[SearchResponse]:
        calls.append(list(queries))
        return [_response() for _ in queries]

    async def observe(_telemetry):
        nonlocal observer_calls
        observer_calls += 1
        return None

    result = await run_bounded_continuation_search(
        ["q1", "q2", "q3"],
        enabled=False,
        requested_search_regime="balanced",
        requested_reserve_queries=1,
        permit=verified_continuation_promotion_permit(),
        search_many=search_many,
        observe_wave=observe,
    )

    assert calls == [["q1", "q2", "q3"]]
    assert observer_calls == 0
    assert result.executed_queries == ["q1", "q2", "q3"]
    assert result.reserve_reordered is False


@pytest.mark.asyncio
async def test_auto_regime_fails_open_to_legacy_single_wave_even_when_gate_enabled():
    calls: list[list[str]] = []

    async def search_many(queries: list[str]) -> list[SearchResponse]:
        calls.append(list(queries))
        return [_response() for _ in queries]

    async def observe(_telemetry):
        raise AssertionError("auto regime must not invoke steering observer path")

    result = await run_bounded_continuation_search(
        ["q1", "q2", "q3", "q4"],
        enabled=True,
        requested_search_regime="auto",
        requested_reserve_queries=2,
        permit=verified_continuation_promotion_permit(),
        search_many=search_many,
        observe_wave=observe,
    )

    assert calls == [["q1", "q2", "q3", "q4"]]
    assert result.executed_queries == ["q1", "q2", "q3", "q4"]


@pytest.mark.asyncio
async def test_continuation_reorders_reserve_but_executes_every_original_query_once():
    first = [
        "стоматология красноярск официальный сайт",
        "металлообработка красноярск завод",
    ]
    reserve = [
        "металлообработка завод красноярск оборудование",
        "стоматология клиника красноярск",
    ]
    calls: list[list[str]] = []

    async def search_many(queries: list[str]) -> list[SearchResponse]:
        calls.append(list(queries))
        return [_response() for _ in queries]

    async def observe(_telemetry):
        return SearchObserverRecommendation(
            sufficient_evidence=True,
            recommendations=[
                DirectionRecommendation(
                    direction_index=0,
                    action=ObserverAction.CONTINUE,
                    confidence=0.9,
                    rationale="productive continuation",
                )
            ],
            summary="continue productive direction",
        )

    result = await run_bounded_continuation_search(
        first + reserve,
        enabled=True,
        requested_search_regime="balanced",
        requested_reserve_queries=2,
        permit=verified_continuation_promotion_permit(),
        search_many=search_many,
        observe_wave=observe,
    )

    assert calls[0] == first
    assert calls[1] == [
        "стоматология клиника красноярск",
        "металлообработка завод красноярск оборудование",
    ]
    assert set(result.executed_queries) == set(first + reserve)
    assert len(result.executed_queries) == len(first + reserve)
    assert result.reserve_reordered is True
    assert result.steering_decision is not None
    assert result.steering_decision.accepted_direction_indexes == [0]


@pytest.mark.asyncio
async def test_observer_failure_keeps_all_reserve_queries_in_original_order():
    calls: list[list[str]] = []

    async def search_many(queries: list[str]) -> list[SearchResponse]:
        calls.append(list(queries))
        return [_response() for _ in queries]

    async def observe(_telemetry):
        return None

    result = await run_bounded_continuation_search(
        ["q1 alpha", "q2 beta", "q3 alpha", "q4 beta"],
        enabled=True,
        requested_search_regime="precision",
        requested_reserve_queries=2,
        permit=verified_continuation_promotion_permit(),
        search_many=search_many,
        observe_wave=observe,
    )

    assert calls == [["q1 alpha", "q2 beta"], ["q3 alpha", "q4 beta"]]
    assert result.executed_queries == ["q1 alpha", "q2 beta", "q3 alpha", "q4 beta"]
    assert result.reserve_reordered is False
    assert result.steering_decision is not None
    assert result.steering_decision.reason_codes == ["no_eligible_continuation_recommendations"]
