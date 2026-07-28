from __future__ import annotations

import base64
import json
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

import httpx
import pytest

from app.search_gateway.cache import MemorySearchCache
from app.search_gateway.gateway import SearchGateway, canonical_url
from app.search_gateway.models import (
    AttemptState,
    FallbackReason,
    GatewayState,
    SearchItem,
    SearchPolicy,
    SearchRequest,
)
from app.search_gateway.providers import (
    ProviderError,
    SearchProvider,
    SearxngProvider,
    TavilyProvider,
    YandexProvider,
)


def request(query: str = "тестовая компания") -> SearchRequest:
    return SearchRequest(
        query=query,
        limit=5,
        mission_id="mission-provider-test",
        correlation_id="correlation-provider-test",
    )


def _transport_for(provider: str) -> httpx.MockTransport:
    def handler(incoming: httpx.Request) -> httpx.Response:
        if provider == "searxng":
            assert incoming.method == "GET"
            assert incoming.url.params["format"] == "json"
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "url": "https://example.ru/about?utm_source=test",
                            "title": "Example",
                            "content": "Описание",
                        }
                    ]
                },
            )
        if provider == "tavily":
            assert incoming.method == "POST"
            assert incoming.headers["Authorization"] == "Bearer secret-tavily"
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "url": "https://example.ru/about",
                            "title": "Example",
                            "content": "Описание",
                        }
                    ]
                },
            )
        assert incoming.method == "POST"
        assert incoming.headers["Authorization"] == "Api-Key secret-yandex"
        xml = (
            "<?xml version='1.0' encoding='utf-8'?>"
            "<yandexsearch><response><results><grouping><group><doc>"
            "<url>https://example.ru/about</url>"
            "<title>Example</title><passages><passage>Описание</passage></passages>"
            "</doc></group></grouping></results></response></yandexsearch>"
        )
        return httpx.Response(
            200,
            json={"rawData": base64.b64encode(xml.encode()).decode()},
        )

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_name", ["searxng", "yandex", "tavily"])
async def test_all_three_adapters_implement_the_same_contract(provider_name):
    if provider_name == "searxng":
        provider = SearxngProvider(
            "https://search.internal",
            transport=_transport_for(provider_name),
        )
    elif provider_name == "yandex":
        provider = YandexProvider(
            "secret-yandex",
            "folder",
            cost_amount=Decimal("1"),
            transport=_transport_for(provider_name),
        )
    else:
        provider = TavilyProvider(
            "secret-tavily",
            cost_amount=Decimal("0.01"),
            transport=_transport_for(provider_name),
        )

    results = await provider.search(request(), timeout_seconds=1)

    assert len(results) == 1
    assert isinstance(results[0], SearchItem)
    assert str(results[0].url).startswith("https://example.ru/about")
    assert results[0].provider == provider_name


class StubProvider(SearchProvider):
    def __init__(
        self,
        name: str,
        *,
        results: list[SearchItem] | None = None,
        error: ProviderError | None = None,
        paid: bool = False,
        cost_amount: Decimal = Decimal("0"),
    ) -> None:
        self.name = name
        self.results = results or []
        self.error = error
        self.paid = paid
        self.cost_amount = cost_amount
        self.cost_currency = "USD"
        self.calls = 0

    @property
    def configured(self) -> bool:
        return True

    async def search(self, request: SearchRequest, *, timeout_seconds: float) -> list[SearchItem]:
        self.calls += 1
        if self.error:
            raise self.error
        return self.results


@pytest.mark.asyncio
async def test_provider_failure_falls_back_and_marks_degraded():
    primary = StubProvider("primary", error=ProviderError("safe failure", retryable=False))
    fallback = StubProvider(
        "fallback",
        results=[
            SearchItem(
                url="https://example.ru/?utm_source=x",
                title="Example",
                snippet="Result",
                provider="fallback",
            ),
            SearchItem(
                url="https://example.ru#duplicate",
                title="Duplicate",
                snippet="Duplicate",
                provider="fallback",
            ),
        ],
    )
    gateway = SearchGateway([primary, fallback])

    response = await gateway.search(
        request(),
        SearchPolicy(provider_order=("primary", "fallback")),
    )

    assert response.diagnostics.state == GatewayState.DEGRADED
    assert response.diagnostics.selected_provider == "fallback"
    assert response.diagnostics.fallback_used is True
    assert len(response.results) == 1
    assert str(response.results[0].url) == "https://example.ru/"
    assert response.diagnostics.attempts[0].reason == FallbackReason.PROVIDER_ERROR


@pytest.mark.asyncio
async def test_paid_fallback_is_fail_closed_without_policy_and_budget():
    primary = StubProvider("primary", error=ProviderError("failed", retryable=False))
    paid = StubProvider(
        "paid",
        paid=True,
        cost_amount=Decimal("1"),
        results=[
            SearchItem(
                url="https://paid.example/",
                provider="paid",
            )
        ],
    )
    gateway = SearchGateway([primary, paid])

    blocked = await gateway.search(
        request(),
        SearchPolicy(provider_order=("primary", "paid")),
    )

    assert blocked.results == []
    assert paid.calls == 0
    assert blocked.diagnostics.attempts[-1].reason == FallbackReason.POLICY_BLOCKED

    allowed = await gateway.search(
        request("другой запрос"),
        SearchPolicy(
            provider_order=("primary", "paid"),
            allow_paid_fallback=True,
            max_cost_by_currency={"USD": Decimal("1")},
        ),
    )
    assert allowed.results
    assert allowed.diagnostics.total_cost_by_currency["USD"] == Decimal("1")


@pytest.mark.asyncio
async def test_cache_precedes_providers_and_does_not_charge_twice():
    provider = StubProvider(
        "free",
        results=[SearchItem(url="https://cache.example/", provider="free")],
    )
    gateway = SearchGateway([provider], cache=MemorySearchCache())
    policy = SearchPolicy(provider_order=("free",), cache_ttl_seconds=60)

    first = await gateway.search(request(), policy)
    second = await gateway.search(request(), policy)

    assert first.diagnostics.cache_hit is False
    assert second.diagnostics.cache_hit is True
    assert second.diagnostics.selected_provider == "cache"
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_circuit_breaker_skips_repeatedly_failing_provider():
    provider = StubProvider("unstable", error=ProviderError("failed", retryable=False))
    gateway = SearchGateway([provider], failure_threshold=1, recovery_seconds=60)
    policy = SearchPolicy(provider_order=("unstable",), retries=0)

    first = await gateway.search(request("first"), policy)
    second = await gateway.search(request("second"), policy)

    assert first.diagnostics.attempts[0].state == AttemptState.FAILED
    assert second.diagnostics.attempts[0].state == AttemptState.SKIPPED
    assert second.diagnostics.attempts[0].reason == FallbackReason.CIRCUIT_OPEN
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_paid_retry_cannot_exceed_mission_budget():
    provider = StubProvider(
        "paid",
        paid=True,
        cost_amount=Decimal("1"),
        error=ProviderError("retryable", retryable=True),
    )
    gateway = SearchGateway([provider])

    response = await gateway.search(
        request("budgeted retry"),
        SearchPolicy(
            provider_order=("paid",),
            retries=1,
            max_cost_by_currency={"USD": Decimal("1")},
        ),
    )

    assert provider.calls == 1
    assert response.diagnostics.attempts[0].reason == FallbackReason.BUDGET_EXCEEDED
    assert response.diagnostics.total_cost_by_currency["USD"] == Decimal("1")


@pytest.mark.asyncio
async def test_global_quota_blocks_calls_after_limit():
    provider = StubProvider(
        "limited",
        results=[SearchItem(url="https://quota.example/", provider="limited")],
    )
    gateway = SearchGateway([provider], global_quotas={"limited": 1})
    policy = SearchPolicy(provider_order=("limited",), cache_ttl_seconds=0)

    first = await gateway.search(request("quota one"), policy)
    second = await gateway.search(request("quota two"), policy)

    assert first.results
    assert second.results == []
    assert second.diagnostics.attempts[0].reason == FallbackReason.QUOTA_EXCEEDED
    assert provider.calls == 1


def test_canonical_url_removes_tracking_and_preserves_semantic_query():
    assert canonical_url(
        "HTTPS://Example.RU:443/path/?utm_source=x&b=2&a=1#fragment"
    ) == "https://example.ru/path?a=1&b=2"


@pytest.mark.asyncio
async def test_benchmark_5_records_recall_latency_and_cost_without_secrets():
    fixture = json.loads(
        (
            Path(__file__).parents[1]
            / "benchmarks"
            / "sef"
            / "provider-gateway-5-v0.1.json"
        ).read_text(encoding="utf-8")
    )
    expected = {case["query"]: case["expected_host"] for case in fixture["cases"]}

    class BenchmarkProvider(StubProvider):
        async def search(self, request: SearchRequest, *, timeout_seconds: float) -> list[SearchItem]:
            self.calls += 1
            return [
                SearchItem(
                    url=f"https://{expected[request.query]}/contacts",
                    title=request.query,
                    provider=self.name,
                )
            ]

    provider = BenchmarkProvider("benchmark", cost_amount=Decimal("0"))
    gateway = SearchGateway([provider])
    hits = 0
    latency: list[int] = []
    total_cost = Decimal("0")
    for case in fixture["cases"]:
        response = await gateway.search(
            request(case["query"]),
            SearchPolicy(provider_order=("benchmark",), cache_ttl_seconds=0),
        )
        host = urlparse(str(response.results[0].url)).hostname
        hits += int(host == case["expected_host"])
        latency.extend(attempt.latency_ms for attempt in response.diagnostics.attempts)
        total_cost += sum(response.diagnostics.total_cost_by_currency.values(), Decimal("0"))

    serialized = json.dumps(
        {
            "recall": hits / len(fixture["cases"]),
            "latency_ms": latency,
            "cost": str(total_cost),
        }
    )
    assert hits == 5
    assert len(latency) == 5
    assert "secret-" not in serialized


def test_health_never_exposes_provider_credentials():
    gateway = SearchGateway(
        [
            YandexProvider("secret-yandex", "folder", cost_amount=Decimal("1")),
            TavilyProvider("secret-tavily", cost_amount=Decimal("1")),
        ]
    )

    payload = json.dumps([item.model_dump(mode="json") for item in gateway.health()])

    assert "secret-yandex" not in payload
    assert "secret-tavily" not in payload
    assert all("configured" in item.model_dump() for item in gateway.health())
