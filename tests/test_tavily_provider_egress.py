from __future__ import annotations

from decimal import Decimal

import httpx
import pytest

from app.search_gateway.gateway import SearchGateway
from app.search_gateway.models import AttemptState, FallbackReason, ProviderReadiness, SearchPolicy, SearchRequest
from app.search_gateway.providers import ProviderError, TavilyProvider


def _request(query: str = "Красноярск стоматология") -> SearchRequest:
    return SearchRequest(
        query=query,
        limit=5,
        mission_id="mission-tavily-egress-test",
        correlation_id="correlation-tavily-egress-test",
    )


@pytest.mark.asyncio
async def test_tavily_proxy_is_provider_local_and_never_needed_with_mock_transport() -> None:
    seen = {"calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["calls"] += 1
        assert request.url.host == "api.tavily.com"
        assert request.headers["Authorization"] == "Bearer test-token"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "url": "https://clinic.example/",
                        "title": "Clinic",
                        "content": "Стоматология Красноярск",
                    }
                ]
            },
        )

    provider = TavilyProvider(
        "test-token",
        cost_amount=Decimal("0.008"),
        proxy_url="http://proxy-user:proxy-password@51.241.23.14:50100",
        transport=httpx.MockTransport(handler),
        contract_allowed=True,
    )

    results = await provider.search(_request(), timeout_seconds=1)

    assert seen["calls"] == 1
    assert provider.proxy_configured is True
    assert len(results) == 1
    assert results[0].provider == "tavily"


@pytest.mark.asyncio
async def test_tavily_contract_gate_blocks_before_network_and_paid_accounting() -> None:
    seen = {"calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["calls"] += 1
        return httpx.Response(200, json={"results": []})

    provider = TavilyProvider(
        "test-token",
        cost_amount=Decimal("0.008"),
        transport=httpx.MockTransport(handler),
        contract_allowed=False,
    )
    gateway = SearchGateway([provider])

    assert provider.technical_configured is True
    assert provider.contract_allowed is False
    assert provider.configured is True
    assert provider.execution_allowed is False

    health = gateway.health(
        SearchPolicy(
            provider_order=("tavily",),
            allowed_providers=frozenset({"tavily"}),
            max_cost_by_currency={"USD": Decimal("100")},
        )
    )
    assert health[0].state == ProviderReadiness.CONTRACT_BLOCKED
    assert health[0].configured is True
    assert health[0].ready is False

    response = await gateway.search(
        _request("contract gate"),
        SearchPolicy(
            provider_order=("tavily",),
            max_cost_by_currency={"USD": Decimal("100")},
            cache_ttl_seconds=0,
        ),
    )

    assert seen["calls"] == 0
    assert response.results == []
    assert response.diagnostics.total_cost_by_currency == {}
    assert response.diagnostics.attempts[0].state == AttemptState.SKIPPED
    assert response.diagnostics.attempts[0].reason == FallbackReason.CONTRACT_BLOCKED

    with pytest.raises(ProviderError) as exc_info:
        await provider.search(_request("direct blocked"), timeout_seconds=1)
    assert exc_info.value.reason == FallbackReason.CONTRACT_BLOCKED
    assert "51.241.23.14" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_tavily_http_client_receives_explicit_proxy_without_exposing_it(monkeypatch) -> None:
    captured: dict[str, object] = {}
    proxy_url = "http://proxy-user:proxy-password@51.241.23.14:50100"

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method: str, url: str, **kwargs):
            captured["method"] = method
            captured["url"] = url
            return httpx.Response(
                200,
                request=httpx.Request(method, url),
                json={"results": []},
            )

    monkeypatch.setattr("app.search_gateway.providers.httpx.AsyncClient", FakeAsyncClient)

    provider = TavilyProvider(
        "test-token",
        cost_amount=Decimal("0.008"),
        proxy_url=proxy_url,
        contract_allowed=True,
    )
    await provider.search(_request("proxy construction"), timeout_seconds=3)

    assert captured["proxy"] == proxy_url
    assert captured["trust_env"] is False
    assert captured["timeout"] == 3
    assert "transport" not in captured
    assert proxy_url not in repr(provider.__dict__.keys())
