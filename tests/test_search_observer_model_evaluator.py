from decimal import Decimal

import pytest

from app.search_observer import QueryYieldTelemetry, SearchWaveTelemetry
from app.search_observer_llm import evaluate_search_wave_shadow_with_model
from app.search_observer_models import ObserverProvider, ResolvedObserverModel


def telemetry():
    return SearchWaveTelemetry(
        query_count=1,
        result_count=4,
        unique_domain_count=4,
        duplicate_domain_ratio=0.0,
        provider_result_counts={"searxng": 2, "yandex": 2},
        attempt_states={"succeeded": 2},
        latency_ms_total=100,
        degraded_attempts=0,
        total_cost_by_currency={"RUB": Decimal("0.01")},
        directions=[QueryYieldTelemetry(
            query="test query",
            result_count=4,
            unique_domain_count=4,
            duplicate_domain_ratio=0.0,
            provider_result_counts={"searxng": 2, "yandex": 2},
            attempt_states={"succeeded": 2},
            latency_ms_total=100,
            degraded_attempts=0,
            cache_hit=False,
            total_cost_by_currency={"RUB": Decimal("0.01")},
        )],
    )


@pytest.mark.asyncio
async def test_unconfigured_model_fails_open_without_http_call(monkeypatch):
    called = False

    class Client:
        async def __aenter__(self):
            nonlocal called
            called = True
            return self

        async def __aexit__(self, *args):
            return None

    monkeypatch.setattr("app.search_observer_llm.httpx.AsyncClient", Client)
    model = ResolvedObserverModel(
        profile_name="qwen-flash",
        provider=ObserverProvider.QWEN,
        base_url="",
        api_key="",
        model="",
        tier="O1",
        configured=False,
    )
    assert await evaluate_search_wave_shadow_with_model(telemetry(), model) is None
    assert called is False


@pytest.mark.asyncio
async def test_generic_model_uses_resolved_endpoint_and_preserves_shadow(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [{"message": {"content": '{"observer_mode":"shadow","routing_changed":false,"sufficient_evidence":true,"recommendations":[{"direction_index":0,"action":"continue","confidence":0.8,"rationale":"yield is healthy","refined_queries":[]}],"summary":"continue"}'}}]
            }

    class Client:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, headers, json):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return Response()

    monkeypatch.setattr("app.search_observer_llm.httpx.AsyncClient", Client)
    model = ResolvedObserverModel(
        profile_name="glm-flash",
        provider=ObserverProvider.GLM,
        base_url="https://glm.example/v1",
        api_key="secret",
        model="glm-test",
        tier="O1",
        configured=True,
    )
    result = await evaluate_search_wave_shadow_with_model(telemetry(), model)
    assert result is not None
    assert result.routing_changed is False
    assert result.recommendations[0].action == "continue"
    assert captured["url"] == "https://glm.example/v1/chat/completions"
    assert captured["json"]["model"] == "glm-test"
