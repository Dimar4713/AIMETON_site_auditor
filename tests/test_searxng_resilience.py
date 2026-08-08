from __future__ import annotations

import httpx
import pytest

from app.search_gateway.models import FallbackReason, SearchRequest
from app.search_gateway.providers import ProviderError, SearxngProvider


def _request() -> SearchRequest:
    return SearchRequest(
        query='site:example.org "Example"',
        limit=10,
        mission_id="mission-searx-resilience",
        correlation_id="corr-searx-resilience",
    )


@pytest.mark.asyncio
async def test_explicit_engine_pool_is_sent_to_searxng() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["engines"] == "brave,duckduckgo,bing"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "url": "https://example.org/",
                        "title": "Example",
                        "content": "Example result",
                    }
                ],
                "unresponsive_engines": [["brave", "too many requests"]],
            },
        )

    provider = SearxngProvider(
        "https://search.internal",
        engines=("brave", "duckduckgo", "bing"),
        transport=httpx.MockTransport(handler),
    )

    results = await provider.search(_request(), timeout_seconds=1)

    assert len(results) == 1
    assert str(results[0].url) == "https://example.org/"


@pytest.mark.asyncio
async def test_true_empty_result_stays_empty_when_upstreams_are_responsive() -> None:
    provider = SearxngProvider(
        "https://search.internal",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={"results": [], "unresponsive_engines": []},
            )
        ),
    )

    assert await provider.search(_request(), timeout_seconds=1) == []


@pytest.mark.asyncio
async def test_zero_results_with_antibot_upstream_failures_is_not_tightly_retried() -> None:
    provider = SearxngProvider(
        "https://search.internal",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "results": [],
                    "unresponsive_engines": [
                        ["brave", "Suspended: too many requests"],
                        ["duckduckgo", "CAPTCHA"],
                    ],
                },
            )
        ),
    )

    with pytest.raises(ProviderError) as caught:
        await provider.search(_request(), timeout_seconds=1)

    assert caught.value.retryable is False
    assert caught.value.reason == FallbackReason.CAPTCHA
    assert "upstream engines unavailable" in str(caught.value)
    assert "brave" in str(caught.value)
    assert "duckduckgo" in str(caught.value)


@pytest.mark.asyncio
async def test_partial_results_survive_some_engine_failures() -> None:
    provider = SearxngProvider(
        "https://search.internal",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "url": "https://example.org/about",
                            "title": "Example",
                            "content": "Useful result",
                        }
                    ],
                    "unresponsive_engines": [["startpage", "CAPTCHA"]],
                },
            )
        ),
    )

    results = await provider.search(_request(), timeout_seconds=1)

    assert len(results) == 1
    assert str(results[0].url) == "https://example.org/about"
