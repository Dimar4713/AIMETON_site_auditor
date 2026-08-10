from __future__ import annotations

from dataclasses import dataclass

import httpx
import pytest

from app.search_gateway.models import FallbackReason, SearchRequest
from app.search_gateway.providers import ProviderError, SearxngProvider


ENGINES = ("brave", "duckduckgo", "bing")


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
        mission_id="mission-engine-cooldown",
        correlation_id=f"corr-{query}",
    )


@pytest.mark.asyncio
async def test_partial_captcha_temporarily_removes_only_failed_engine() -> None:
    clock = FakeClock()
    calls: list[tuple[str, ...]] = []
    blocked_engine: str | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal blocked_engine
        selected = tuple(request.url.params["engines"].split(","))
        calls.append(selected)
        if blocked_engine is None:
            blocked_engine = selected[0]
            return httpx.Response(
                200,
                json={
                    "results": [{"url": "https://one.example/", "title": "one", "content": "one"}],
                    "unresponsive_engines": [[blocked_engine, "CAPTCHA"]],
                },
            )
        return httpx.Response(
            200,
            json={
                "results": [{"url": "https://two.example/", "title": "two", "content": "two"}],
                "unresponsive_engines": [],
            },
        )

    provider = SearxngProvider(
        "https://search.internal",
        engines=ENGINES,
        engine_fanout=2,
        engine_block_cooldown_seconds=100.0,
        clock=clock,
        transport=httpx.MockTransport(handler),
    )

    await provider.search(_request("first query"), timeout_seconds=1)
    first_degradation = provider.consume_degradation(_request("unrelated"))
    assert first_degradation is None

    await provider.search(_request("second query"), timeout_seconds=1)

    assert blocked_engine is not None
    assert blocked_engine in calls[0]
    assert blocked_engine not in calls[1]
    assert len(calls[1]) == 2


@pytest.mark.asyncio
async def test_expired_engine_cooldown_restores_deterministic_selection() -> None:
    clock = FakeClock()
    calls: list[tuple[str, ...]] = []
    first = True

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal first
        selected = tuple(request.url.params["engines"].split(","))
        calls.append(selected)
        unresponsive = [[selected[0], "CAPTCHA"]] if first else []
        first = False
        return httpx.Response(
            200,
            json={
                "results": [{"url": "https://example.org/", "title": "ok", "content": "ok"}],
                "unresponsive_engines": unresponsive,
            },
        )

    provider = SearxngProvider(
        "https://search.internal",
        engines=ENGINES,
        engine_fanout=2,
        engine_block_cooldown_seconds=60.0,
        clock=clock,
        transport=httpx.MockTransport(handler),
    )
    request = _request("stable query")

    await provider.search(request, timeout_seconds=1)
    original = calls[0]
    blocked = original[0]
    provider.consume_degradation(request)

    clock.advance(30.0)
    await provider.search(request, timeout_seconds=1)
    assert blocked not in calls[1]

    clock.advance(31.0)
    await provider.search(request, timeout_seconds=1)
    assert calls[2] == original


@pytest.mark.asyncio
async def test_all_engines_in_cooldown_fail_closed_without_http_request() -> None:
    clock = FakeClock()
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        selected = tuple(request.url.params["engines"].split(","))
        return httpx.Response(
            200,
            json={
                "results": [{"url": "https://example.org/", "title": "ok", "content": "ok"}],
                "unresponsive_engines": [[name, "HTTP 403 Access Denied"] for name in selected],
            },
        )

    provider = SearxngProvider(
        "https://search.internal",
        engines=("duckduckgo", "startpage"),
        engine_fanout=2,
        engine_block_cooldown_seconds=100.0,
        clock=clock,
        transport=httpx.MockTransport(handler),
    )
    first_request = _request("prime cooldown")
    await provider.search(first_request, timeout_seconds=1)
    provider.consume_degradation(first_request)

    with pytest.raises(ProviderError) as exc_info:
        await provider.search(_request("while all cooling"), timeout_seconds=1)

    assert exc_info.value.reason is FallbackReason.CIRCUIT_OPEN
    assert exc_info.value.retryable is False
    assert call_count == 1


@pytest.mark.asyncio
async def test_rate_limit_uses_shorter_configured_cooldown_than_block() -> None:
    clock = FakeClock()
    calls: list[tuple[str, ...]] = []
    first = True

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal first
        selected = tuple(request.url.params["engines"].split(","))
        calls.append(selected)
        unresponsive = [[selected[0], "HTTP 429 Too Many Requests"]] if first else []
        first = False
        return httpx.Response(
            200,
            json={
                "results": [{"url": "https://example.org/", "title": "ok", "content": "ok"}],
                "unresponsive_engines": unresponsive,
            },
        )

    provider = SearxngProvider(
        "https://search.internal",
        engines=ENGINES,
        engine_fanout=2,
        engine_rate_limit_cooldown_seconds=20.0,
        engine_block_cooldown_seconds=100.0,
        clock=clock,
        transport=httpx.MockTransport(handler),
    )
    request = _request("rate limited query")

    await provider.search(request, timeout_seconds=1)
    original = calls[0]
    blocked = original[0]
    provider.consume_degradation(request)

    clock.advance(10.0)
    await provider.search(request, timeout_seconds=1)
    assert blocked not in calls[1]

    clock.advance(11.0)
    await provider.search(request, timeout_seconds=1)
    assert calls[2] == original
