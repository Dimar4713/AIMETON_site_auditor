from __future__ import annotations

import httpx
import pytest

from app.search_gateway.models import SearchRequest
from app.search_gateway.providers import SearxngProvider


ENGINES = ("brave", "duckduckgo", "google cse", "startpage", "bing")


def _request(query: str) -> SearchRequest:
    return SearchRequest(
        query=query,
        limit=10,
        language="ru-RU",
        mission_id="mission-engine-fanout",
        correlation_id=f"corr-{query}",
    )


@pytest.mark.asyncio
async def test_bounded_engine_fanout_sends_only_configured_subset() -> None:
    seen: list[tuple[str, ...]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        selected = tuple(request.url.params["engines"].split(","))
        seen.append(selected)
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
                "unresponsive_engines": [],
            },
        )

    provider = SearxngProvider(
        "https://search.internal",
        engines=ENGINES,
        engine_fanout=2,
        transport=httpx.MockTransport(handler),
    )

    await provider.search(_request("стоматология красноярск"), timeout_seconds=1)

    assert len(seen) == 1
    assert len(seen[0]) == 2
    assert len(set(seen[0])) == 2
    assert set(seen[0]).issubset(ENGINES)


@pytest.mark.asyncio
async def test_engine_selection_is_stable_for_same_query_and_policy() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params["engines"])
        return httpx.Response(200, json={"results": [], "unresponsive_engines": []})

    provider = SearxngProvider(
        "https://search.internal",
        engines=ENGINES,
        engine_fanout=2,
        transport=httpx.MockTransport(handler),
    )
    request = _request("лучшие стоматологии красноярск")

    await provider.search(request, timeout_seconds=1)
    await provider.search(request, timeout_seconds=1)

    assert seen[0] == seen[1]


@pytest.mark.asyncio
async def test_distinct_queries_distribute_work_across_full_engine_pool() -> None:
    selected: set[str] = set()

    def handler(request: httpx.Request) -> httpx.Response:
        selected.update(request.url.params["engines"].split(","))
        return httpx.Response(200, json={"results": [], "unresponsive_engines": []})

    provider = SearxngProvider(
        "https://search.internal",
        engines=ENGINES,
        engine_fanout=2,
        transport=httpx.MockTransport(handler),
    )

    for index in range(20):
        await provider.search(_request(f"стоматология красноярск вариант {index}"), timeout_seconds=1)

    assert selected == set(ENGINES)


@pytest.mark.asyncio
async def test_fanout_at_or_above_pool_size_preserves_full_pool() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params["engines"])
        return httpx.Response(200, json={"results": [], "unresponsive_engines": []})

    provider = SearxngProvider(
        "https://search.internal",
        engines=ENGINES,
        engine_fanout=len(ENGINES),
        transport=httpx.MockTransport(handler),
    )

    await provider.search(_request("полный пул"), timeout_seconds=1)

    assert seen == [",".join(ENGINES)]


@pytest.mark.asyncio
async def test_provider_without_explicit_fanout_remains_backward_compatible() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params["engines"])
        return httpx.Response(200, json={"results": [], "unresponsive_engines": []})

    provider = SearxngProvider(
        "https://search.internal",
        engines=ENGINES,
        transport=httpx.MockTransport(handler),
    )

    await provider.search(_request("совместимость"), timeout_seconds=1)

    assert seen == [",".join(ENGINES)]
