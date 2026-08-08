from __future__ import annotations

from decimal import Decimal

import httpx
import pytest

from app.search_gateway.gateway import SearchGateway
from app.search_gateway.models import FallbackReason, SearchPolicy, SearchRequest
from app.search_gateway.providers import ProviderError, SearchProvider, SearxngProvider


def request(query: str = "typed failure") -> SearchRequest:
    return SearchRequest(
        query=query,
        limit=5,
        mission_id="mission-typed-failure",
        correlation_id=f"corr-{query}",
    )


def provider_with_response(status: int, body: str = "failure") -> SearxngProvider:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=body)

    return SearxngProvider(
        "https://search.internal",
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "body", "reason"),
    [
        (403, "forbidden", FallbackReason.PROVIDER_BLOCKED),
        (429, "too many requests", FallbackReason.RATE_LIMITED),
        (403, "CAPTCHA verification", FallbackReason.CAPTCHA),
    ],
)
async def test_http_antibot_and_limit_states_are_typed(status, body, reason):
    provider = provider_with_response(status, body)

    with pytest.raises(ProviderError) as caught:
        await provider.search(request(str(status)), timeout_seconds=1)

    assert caught.value.reason == reason
    assert caught.value.retryable is False


@pytest.mark.asyncio
async def test_invalid_json_is_protocol_error_and_not_retried():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json")

    provider = SearxngProvider(
        "https://search.internal",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ProviderError) as caught:
        await provider.search(request("json"), timeout_seconds=1)

    assert caught.value.reason == FallbackReason.PROTOCOL_ERROR
    assert caught.value.retryable is False


@pytest.mark.asyncio
async def test_searx_unresponsive_payload_maps_captcha_state():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [],
                "unresponsive_engines": [["startpage", "CAPTCHA"]],
            },
        )

    provider = SearxngProvider(
        "https://search.internal",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ProviderError) as caught:
        await provider.search(request("searx captcha"), timeout_seconds=1)

    assert caught.value.reason == FallbackReason.CAPTCHA
    assert caught.value.retryable is False


@pytest.mark.asyncio
async def test_searx_generic_unresponsive_state_remains_retryable():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [],
                "unresponsive_engines": [["brave", "network error"]],
            },
        )

    provider = SearxngProvider(
        "https://search.internal",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ProviderError) as caught:
        await provider.search(request("searx transient"), timeout_seconds=1)

    assert caught.value.reason == FallbackReason.PROVIDER_ERROR
    assert caught.value.retryable is True


class TypedFailureProvider(SearchProvider):
    name = "typed"
    paid = False
    cost_amount = Decimal("0")
    cost_currency = "USD"

    def __init__(self, reason: FallbackReason) -> None:
        self.reason = reason
        self.calls = 0

    @property
    def configured(self) -> bool:
        return True

    async def search(self, request: SearchRequest, *, timeout_seconds: float):
        self.calls += 1
        raise ProviderError("typed upstream failure", retryable=False, reason=self.reason)


@pytest.mark.asyncio
async def test_gateway_preserves_typed_reason_and_avoids_tight_retry():
    provider = TypedFailureProvider(FallbackReason.RATE_LIMITED)
    gateway = SearchGateway([provider])

    response = await gateway.search(
        request("gateway typed"),
        SearchPolicy(provider_order=("typed",), retries=3, cache_ttl_seconds=0),
    )

    assert provider.calls == 1
    assert response.diagnostics.attempts[0].reason == FallbackReason.RATE_LIMITED
