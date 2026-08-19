from __future__ import annotations

import pytest

from app import discovery
from app.hunter_search_policy_authority import HunterSearchPolicyAuthority, ResolvedHunterSearchPolicy
from app.models import HuntRequest
from app.search_gateway.models import GatewayState, SearchDiagnostics, SearchPolicy, SearchResponse
from app.search_observer_llm import DirectionRecommendation, ObserverAction, SearchObserverRecommendation


@pytest.fixture(autouse=True)
def _isolated_runtime(monkeypatch, tmp_path):
    monkeypatch.setenv("AIMETON_RUNTIME_DB", str(tmp_path / "runtime.sqlite3"))
    for name in (
        "HUNTER_SEARCH_OBSERVER_STEERING_ENABLED",
        "HUNTER_SEARCH_OBSERVER_STEERING_REGIME",
        "HUNTER_SEARCH_OBSERVER_RESERVE_QUERIES",
        "HUNTER_SEARCH_OBSERVER_SHADOW_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        discovery,
        "resolve_hunter_search_policy",
        lambda: ResolvedHunterSearchPolicy(
            policy=SearchPolicy(),
            authority=HunterSearchPolicyAuthority.ADMIN,
            selected_policy_fingerprint="sha256:test-admin",
            env_policy_fingerprint="sha256:test-env",
            admin_projection_fingerprint="sha256:test-admin",
            policy_equivalent=False,
            admin_policy_persisted=True,
        ),
    )

    async def no_llm_plan(**_kwargs):
        return None

    monkeypatch.setattr(discovery, "generate_hunter_query_plan", no_llm_plan)


def _request() -> HuntRequest:
    return HuntRequest(
        region="Красноярск",
        industries=["Стоматология"],
        max_queries=4,
        results_per_query=1,
        max_candidates=10,
        output_limit=10,
        concurrency=1,
    )


def _empty_response() -> SearchResponse:
    return SearchResponse(
        results=[],
        diagnostics=SearchDiagnostics(state=GatewayState.SUCCESS, selected_provider="fake"),
    )


class _RecordingGateway:
    def __init__(self, events: list[str]):
        self.events = events

    async def search(self, request, _policy):
        self.events.append(f"search:{request.query}")
        return _empty_response()


def test_runtime_steering_defaults_fail_closed_to_off_auto_two_reserve(monkeypatch):
    assert discovery._observer_runtime_steering_config() == (False, "auto", 2)

    monkeypatch.setenv("HUNTER_SEARCH_OBSERVER_STEERING_ENABLED", "true")
    monkeypatch.setenv("HUNTER_SEARCH_OBSERVER_STEERING_REGIME", "unexpected")
    monkeypatch.setenv("HUNTER_SEARCH_OBSERVER_RESERVE_QUERIES", "999")
    assert discovery._observer_runtime_steering_config() == (True, "auto", 10)

    monkeypatch.setenv("HUNTER_SEARCH_OBSERVER_RESERVE_QUERIES", "not-an-int")
    assert discovery._observer_runtime_steering_config() == (True, "auto", 2)


@pytest.mark.asyncio
async def test_default_off_run_hunt_is_single_wave_and_never_calls_observer(monkeypatch):
    queries = ["q1", "q2", "q3", "q4"]
    events: list[str] = []
    monkeypatch.setattr(discovery, "_build_queries", lambda _req: list(queries))
    monkeypatch.setattr(discovery, "get_search_gateway", lambda: _RecordingGateway(events))

    async def forbidden_observer(_telemetry):
        raise AssertionError("default-OFF Hunter must not call Search Observer")

    monkeypatch.setattr(discovery, "evaluate_search_wave_shadow", forbidden_observer)

    result = await discovery.run_hunt(_request())

    assert result.queries == queries
    assert events == [f"search:{query}" for query in queries]
    assert result.discovered == 0


@pytest.mark.asyncio
async def test_enabled_auto_run_hunt_still_preserves_legacy_single_wave(monkeypatch):
    queries = ["q1", "q2", "q3", "q4"]
    events: list[str] = []
    monkeypatch.setenv("HUNTER_SEARCH_OBSERVER_STEERING_ENABLED", "1")
    monkeypatch.setenv("HUNTER_SEARCH_OBSERVER_STEERING_REGIME", "auto")
    monkeypatch.setattr(discovery, "_build_queries", lambda _req: list(queries))
    monkeypatch.setattr(discovery, "get_search_gateway", lambda: _RecordingGateway(events))

    async def forbidden_observer(_telemetry):
        raise AssertionError("auto regime must remain legacy single-wave")

    monkeypatch.setattr(discovery, "evaluate_search_wave_shadow", forbidden_observer)

    result = await discovery.run_hunt(_request())

    assert result.queries == queries
    assert events == [f"search:{query}" for query in queries]


@pytest.mark.asyncio
async def test_enabled_explicit_regime_observes_first_wave_and_executes_every_planned_query_once(monkeypatch):
    queries = [
        "стоматология красноярск официальный сайт",
        "металлообработка красноярск завод",
        "металлообработка завод красноярск оборудование",
        "стоматология клиника красноярск",
    ]
    events: list[str] = []
    monkeypatch.setenv("HUNTER_SEARCH_OBSERVER_STEERING_ENABLED", "true")
    monkeypatch.setenv("HUNTER_SEARCH_OBSERVER_STEERING_REGIME", "balanced")
    monkeypatch.setenv("HUNTER_SEARCH_OBSERVER_RESERVE_QUERIES", "2")
    monkeypatch.setattr(discovery, "_build_queries", lambda _req: list(queries))
    monkeypatch.setattr(discovery, "get_search_gateway", lambda: _RecordingGateway(events))

    async def observer(_telemetry):
        events.append("observer")
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

    monkeypatch.setattr(discovery, "evaluate_search_wave_shadow", observer)

    result = await discovery.run_hunt(_request())

    assert events[:2] == [f"search:{queries[0]}", f"search:{queries[1]}"]
    assert events[2] == "observer"
    searched = [event.removeprefix("search:") for event in events if event.startswith("search:")]
    assert len(searched) == len(queries)
    assert set(searched) == set(queries)
    assert len(set(searched)) == len(queries)
    assert result.queries == searched
