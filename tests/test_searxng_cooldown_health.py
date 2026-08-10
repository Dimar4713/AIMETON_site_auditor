from __future__ import annotations

from dataclasses import dataclass

import httpx
import pytest

from app import main as app_main
from app.search_gateway.gateway import SearchGateway
from app.search_gateway.models import (
    FallbackReason,
    ProviderHealth,
    ProviderReadiness,
    SearchPolicy,
    SearchRequest,
)
from app.search_gateway.providers import SearxngProvider
from app.search_gateway.scheduler import ScheduledProvider


@dataclass
class FakeClock:
    now: float = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _request(query: str) -> SearchRequest:
    return SearchRequest(
        query=query,
        limit=10,
        language="ru-RU",
        mission_id="mission-cooldown-health",
        correlation_id=f"corr-{query}",
    )


@pytest.mark.asyncio
async def test_partial_cooldown_is_visible_without_disabling_healthy_engines() -> None:
    clock = FakeClock()
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "results": [
                    {"url": "https://clinic.example/", "title": "clinic", "content": "clinic"}
                ],
                "unresponsive_engines": [["duckduckgo", "CAPTCHA"]],
            },
        )

    provider = ScheduledProvider(
        SearxngProvider(
            "https://search.internal",
            engines=("duckduckgo", "bing"),
            engine_fanout=2,
            engine_block_cooldown_seconds=100.0,
            clock=clock,
            transport=httpx.MockTransport(handler),
        ),
        max_concurrency=1,
    )
    gateway = SearchGateway([provider])
    policy = SearchPolicy(provider_order=("searxng",), retries=0, cache_ttl_seconds=0)

    await gateway.search(_request("partial cooldown"), policy)
    health = gateway.health(policy)[0]

    assert calls == 1
    assert health.state is ProviderReadiness.ACTIVE
    assert health.ready is True
    assert health.upstream_cooldowns is not None
    assert [item.upstream for item in health.upstream_cooldowns] == ["duckduckgo"]
    assert health.upstream_cooldowns[0].reason is FallbackReason.CAPTCHA
    assert health.upstream_cooldowns[0].retry_after_seconds == 100

    clock.advance(101.0)
    recovered = gateway.health(policy)[0]
    assert recovered.state is ProviderReadiness.ACTIVE
    assert recovered.upstream_cooldowns is None
    assert calls == 1


@pytest.mark.asyncio
async def test_all_engines_cooling_marks_provider_not_ready_without_extra_http() -> None:
    clock = FakeClock()
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        selected = request.url.params["engines"].split(",")
        return httpx.Response(
            200,
            json={
                "results": [
                    {"url": "https://clinic.example/", "title": "clinic", "content": "clinic"}
                ],
                "unresponsive_engines": [
                    [name, "HTTP 429 Too Many Requests"] for name in selected
                ],
            },
        )

    provider = ScheduledProvider(
        SearxngProvider(
            "https://search.internal",
            engines=("duckduckgo", "startpage"),
            engine_fanout=2,
            engine_rate_limit_cooldown_seconds=20.0,
            clock=clock,
            transport=httpx.MockTransport(handler),
        ),
        max_concurrency=1,
    )
    gateway = SearchGateway([provider])
    policy = SearchPolicy(provider_order=("searxng",), retries=0, cache_ttl_seconds=0)

    await gateway.search(_request("all cooling"), policy)
    health = gateway.health(policy)[0]

    assert calls == 1
    assert health.state is ProviderReadiness.CIRCUIT_OPEN
    assert health.ready is False
    assert health.circuit_state == "open"
    assert health.upstream_cooldowns is not None
    assert {item.upstream for item in health.upstream_cooldowns} == {
        "duckduckgo",
        "startpage",
    }
    assert all(
        item.reason is FallbackReason.RATE_LIMITED
        and item.retry_after_seconds == 20
        for item in health.upstream_cooldowns
    )
    assert calls == 1

    clock.advance(21.0)
    recovered = gateway.health(policy)[0]
    assert recovered.state is ProviderReadiness.ACTIVE
    assert recovered.ready is True
    assert recovered.circuit_state == "closed"
    assert recovered.upstream_cooldowns is None
    assert calls == 1


def test_search_health_omits_empty_cooldown_key_for_backward_compatibility(monkeypatch) -> None:
    class FakeGateway:
        def health(self, policy):
            return [
                ProviderHealth(
                    provider="searxng",
                    state=ProviderReadiness.ACTIVE,
                    ready=True,
                    configured=True,
                    paid=False,
                    circuit_state="closed",
                )
            ]

    monkeypatch.setattr(app_main, "get_search_gateway", lambda: FakeGateway())
    monkeypatch.setattr(app_main, "search_policy_from_env", lambda: SearchPolicy())

    payload = app_main.search_health()

    assert payload["status"] == "ok"
    assert "upstream_cooldowns" not in payload["providers"][0]
