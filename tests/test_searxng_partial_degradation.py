from __future__ import annotations

import httpx
import pytest

from app.search_gateway.gateway import SearchGateway
from app.search_gateway.models import (
    AttemptState,
    FallbackReason,
    GatewayState,
    SearchPolicy,
    SearchRequest,
)
from app.search_gateway.providers import SearxngProvider
from app.search_gateway.scheduler import ScheduledProvider
from app.search_gateway.trace_projection import provider_waterfall


def _request(query: str = "стоматология красноярск") -> SearchRequest:
    return SearchRequest(
        query=query,
        limit=10,
        language="ru-RU",
        mission_id="mission-partial-searxng",
        correlation_id=f"corr-{query}",
    )


def _policy() -> SearchPolicy:
    return SearchPolicy(
        provider_order=("searxng",),
        allowed_providers=frozenset({"searxng"}),
        retries=0,
    )


@pytest.mark.asyncio
async def test_partial_results_keep_results_but_mark_gateway_degraded() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "url": "https://clinic.example/",
                        "title": "Clinic",
                        "content": "Dentistry",
                    }
                ],
                "unresponsive_engines": [
                    ["duckduckgo", "CAPTCHA"],
                    ["startpage", "HTTP 429 Too Many Requests"],
                ],
            },
        )

    provider = ScheduledProvider(
        SearxngProvider(
            "https://search.internal",
            engines=("duckduckgo", "startpage"),
            transport=httpx.MockTransport(handler),
        ),
        max_concurrency=1,
    )
    gateway = SearchGateway([provider])

    response = await gateway.search(_request(), _policy())

    assert len(response.results) == 1
    assert response.diagnostics.state is GatewayState.DEGRADED
    attempt = response.diagnostics.attempts[0]
    assert attempt.state is AttemptState.SUCCEEDED
    assert attempt.reason is FallbackReason.CAPTCHA
    assert attempt.degraded_upstreams == ["duckduckgo", "startpage"]

    row = provider_waterfall(response.diagnostics)[0]
    assert row["degraded_upstreams"] == ["duckduckgo", "startpage"]
    assert row["reason"] == "captcha"


@pytest.mark.asyncio
async def test_clean_searxng_results_remain_successful() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "url": "https://clinic.example/",
                        "title": "Clinic",
                        "content": "Dentistry",
                    }
                ],
                "unresponsive_engines": [],
            },
        )

    gateway = SearchGateway(
        [
            ScheduledProvider(
                SearxngProvider(
                    "https://search.internal",
                    engines=("bing",),
                    transport=httpx.MockTransport(handler),
                ),
                max_concurrency=1,
            )
        ]
    )

    response = await gateway.search(_request("чистый запрос"), _policy())

    assert response.diagnostics.state is GatewayState.SUCCESS
    attempt = response.diagnostics.attempts[0]
    assert attempt.state is AttemptState.SUCCEEDED
    assert attempt.reason is None
    assert attempt.degraded_upstreams == []


@pytest.mark.asyncio
async def test_partial_degradation_is_request_scoped_under_concurrency() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params["q"]
        if "one" in query:
            unresponsive = [["duckduckgo", "CAPTCHA"]]
            url = "https://one.example/"
        else:
            unresponsive = [["startpage", "HTTP 429"]]
            url = "https://two.example/"
        return httpx.Response(
            200,
            json={
                "results": [{"url": url, "title": query, "content": query}],
                "unresponsive_engines": unresponsive,
            },
        )

    provider = ScheduledProvider(
        SearxngProvider(
            "https://search.internal",
            engines=("duckduckgo", "startpage"),
            transport=httpx.MockTransport(handler),
        ),
        max_concurrency=2,
    )
    gateway = SearchGateway([provider])

    first, second = await __import__("asyncio").gather(
        gateway.search(_request("one"), _policy()),
        gateway.search(_request("two"), _policy()),
    )

    assert first.diagnostics.attempts[0].reason is FallbackReason.CAPTCHA
    assert first.diagnostics.attempts[0].degraded_upstreams == ["duckduckgo"]
    assert second.diagnostics.attempts[0].reason is FallbackReason.RATE_LIMITED
    assert second.diagnostics.attempts[0].degraded_upstreams == ["startpage"]
