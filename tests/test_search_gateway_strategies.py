from __future__ import annotations

from decimal import Decimal

import pytest

from app.search_gateway.gateway import SearchGateway
from app.search_gateway.models import SearchItem, SearchPolicy, SearchRequest, SearchStrategy
from app.search_gateway.providers import SearchProvider


class FakeProvider(SearchProvider):
    paid = False
    cost_amount = Decimal("0")
    cost_currency = "USD"

    def __init__(self, name: str, urls: list[str]) -> None:
        self.name = name
        self.urls = urls
        self.calls = 0

    @property
    def configured(self) -> bool:
        return True

    async def search(self, request: SearchRequest, *, timeout_seconds: float) -> list[SearchItem]:
        self.calls += 1
        return [
            SearchItem(url=url, title=f"{self.name}-{idx}", snippet="", provider=self.name)
            for idx, url in enumerate(self.urls[: request.limit], start=1)
        ]


def request(limit: int = 2) -> SearchRequest:
    return SearchRequest(
        query="стоматология Красноярск",
        limit=limit,
        mission_id="hunt-test",
        correlation_id="corr-test",
    )


@pytest.mark.asyncio
async def test_primary_only_calls_one_available_provider() -> None:
    first = FakeProvider("first", ["https://a.example/"])
    second = FakeProvider("second", ["https://b.example/"])
    gateway = SearchGateway([first, second])

    response = await gateway.search(
        request(),
        SearchPolicy(
            provider_order=("first", "second"),
            strategy=SearchStrategy.PRIMARY_ONLY,
            max_providers_per_query=2,
        ),
    )

    assert [str(item.url) for item in response.results] == ["https://a.example/"]
    assert first.calls == 1
    assert second.calls == 0


@pytest.mark.asyncio
async def test_fallback_first_nonempty_preserves_existing_semantics() -> None:
    first = FakeProvider("first", [])
    second = FakeProvider("second", ["https://b.example/"])
    third = FakeProvider("third", ["https://c.example/"])
    gateway = SearchGateway([first, second, third])

    response = await gateway.search(
        request(),
        SearchPolicy(
            provider_order=("first", "second", "third"),
            strategy=SearchStrategy.FALLBACK_FIRST_NONEMPTY,
            max_providers_per_query=3,
        ),
    )

    assert [item.provider for item in response.results] == ["second"]
    assert (first.calls, second.calls, third.calls) == (1, 1, 0)


@pytest.mark.asyncio
async def test_cascade_until_target_merges_until_unique_target_reached() -> None:
    first = FakeProvider("first", ["https://a.example/"])
    second = FakeProvider("second", ["https://b.example/"])
    third = FakeProvider("third", ["https://c.example/"])
    gateway = SearchGateway([first, second, third])

    response = await gateway.search(
        request(limit=1),
        SearchPolicy(
            provider_order=("first", "second", "third"),
            strategy=SearchStrategy.CASCADE_UNTIL_TARGET,
            target_results=2,
            max_providers_per_query=3,
        ),
    )

    assert {str(item.url) for item in response.results} == {"https://a.example/", "https://b.example/"}
    assert (first.calls, second.calls, third.calls) == (1, 1, 0)
    assert response.diagnostics.selected_provider == "first+second"


@pytest.mark.asyncio
async def test_sequential_union_calls_all_allowed_and_deduplicates() -> None:
    first = FakeProvider("first", ["https://a.example/", "https://shared.example/?utm_source=x"])
    second = FakeProvider("second", ["https://shared.example/", "https://b.example/"])
    third = FakeProvider("third", ["https://c.example/"])
    gateway = SearchGateway([first, second, third])

    response = await gateway.search(
        request(limit=2),
        SearchPolicy(
            provider_order=("first", "second", "third"),
            strategy=SearchStrategy.SEQUENTIAL_UNION,
            target_results=5,
            max_providers_per_query=3,
        ),
    )

    urls = [str(item.url) for item in response.results]
    assert set(urls) == {
        "https://a.example/",
        "https://shared.example/",
        "https://b.example/",
        "https://c.example/",
    }
    assert (first.calls, second.calls, third.calls) == (1, 1, 1)


@pytest.mark.asyncio
async def test_cache_is_strategy_sensitive() -> None:
    first = FakeProvider("first", ["https://a.example/"])
    second = FakeProvider("second", ["https://b.example/"])
    gateway = SearchGateway([first, second])

    await gateway.search(
        request(),
        SearchPolicy(provider_order=("first", "second"), strategy=SearchStrategy.PRIMARY_ONLY),
    )
    response = await gateway.search(
        request(),
        SearchPolicy(
            provider_order=("first", "second"),
            strategy=SearchStrategy.SEQUENTIAL_UNION,
            target_results=2,
            max_providers_per_query=2,
        ),
    )

    assert {str(item.url) for item in response.results} == {"https://a.example/", "https://b.example/"}
    assert second.calls == 1
