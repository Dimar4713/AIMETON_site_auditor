import asyncio
import json

import pytest

from app.search_observer import SearchWaveTelemetry
from app.search_observer_models import ResolvedObserverModel
from scripts.search_observer_model_arena_replay import load_cases, resolved_profiles, run_arena


def _telemetry() -> SearchWaveTelemetry:
    return SearchWaveTelemetry.model_validate(
        {
            "query_count": 1,
            "result_count": 10,
            "unique_domain_count": 8,
            "duplicate_domain_ratio": 0.2,
            "provider_result_counts": {"searxng": 5, "yandex": 5},
            "attempt_states": {"succeeded": 2},
            "latency_ms_total": 200,
            "degraded_attempts": 0,
            "total_cost_by_currency": {"RUB": "0.01"},
            "directions": [
                {
                    "query": "стоматология Красноярск официальный сайт",
                    "result_count": 10,
                    "unique_domain_count": 8,
                    "duplicate_domain_ratio": 0.2,
                    "provider_result_counts": {"searxng": 5, "yandex": 5},
                    "attempt_states": {"succeeded": 2},
                    "latency_ms_total": 200,
                    "degraded_attempts": 0,
                    "cache_hit": False,
                    "total_cost_by_currency": {"RUB": "0.01"},
                }
            ],
        }
    )


def test_load_cases_requires_replay_complete_telemetry(tmp_path) -> None:
    payload = {
        "schema_version": 1,
        "mission_id": "dentistry-krasnoyarsk",
        "attempt_id": "wave-1",
        "telemetry": _telemetry().model_dump(mode="json"),
    }
    (tmp_path / "case.json").write_text(json.dumps(payload), encoding="utf-8")
    cases = load_cases(tmp_path)
    assert len(cases) == 1
    assert cases[0].scenario_slug == "dentistry-krasnoyarsk"
    assert cases[0].telemetry.directions[0].query.startswith("стоматология")


def test_load_cases_rejects_empty_directory(tmp_path) -> None:
    with pytest.raises(ValueError, match="no_cases"):
        load_cases(tmp_path)


def test_resolved_profiles_rejects_unknown_name() -> None:
    with pytest.raises(ValueError, match="unknown_model_profiles"):
        resolved_profiles({"not-a-profile"})


def test_run_arena_rejects_unsafe_bounds() -> None:
    with pytest.raises(ValueError, match="concurrency_out_of_range"):
        asyncio.run(run_arena([], [], max_concurrency=0))
    with pytest.raises(ValueError, match="call_timeout_out_of_range"):
        asyncio.run(run_arena([], [], call_timeout_seconds=0.009))


def test_run_arena_records_timeout_without_aborting(monkeypatch) -> None:
    from scripts import search_observer_model_arena_replay as replay

    async def slow_evaluator(*, case, model, evaluator):
        await asyncio.sleep(0.05)
        raise AssertionError("wait_for should time out first")

    monkeypatch.setattr(replay, "evaluate_model_arena_case", slow_evaluator)
    case = replay.ModelArenaCase(scenario_slug="case-1", telemetry=_telemetry())
    model = ResolvedObserverModel(
        profile_name="test-model",
        provider="routerai",
        base_url="https://example.test/v1",
        api_key="secret",
        model="test/model",
        tier="O1",
        configured=True,
    )
    results = asyncio.run(
        run_arena([case], [model], max_concurrency=1, call_timeout_seconds=0.01)
    )
    assert len(results) == 1
    assert results[0].error_code == "arena_call_timeout"
    assert results[0].schema_valid is False
    assert results[0].routing_changed is False


def test_run_arena_honors_bounded_concurrency(monkeypatch) -> None:
    from scripts import search_observer_model_arena_replay as replay

    active = 0
    peak = 0

    async def fake_evaluator(*, case, model, evaluator):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.02)
        active -= 1
        return replay.observation_from_recommendation(
            scenario_slug=case.scenario_slug,
            model=model,
            latency_ms=20,
            recommendation=None,
            error_code="synthetic",
        )

    monkeypatch.setattr(replay, "evaluate_model_arena_case", fake_evaluator)
    cases = [replay.ModelArenaCase(scenario_slug=f"case-{i}", telemetry=_telemetry()) for i in range(4)]
    model = ResolvedObserverModel(
        profile_name="test-model",
        provider="routerai",
        base_url="https://example.test/v1",
        api_key="secret",
        model="test/model",
        tier="O1",
        configured=True,
    )
    results = asyncio.run(
        run_arena(cases, [model], max_concurrency=2, call_timeout_seconds=1.0)
    )
    assert len(results) == 4
    assert peak == 2
