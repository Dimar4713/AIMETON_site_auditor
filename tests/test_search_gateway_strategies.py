from __future__ import annotations

from decimal import Decimal

import pytest

from app.search_gateway.gateway import SearchGateway, request_fingerprint
from app.search_gateway.models import (
    FallbackReason,
    SearchItem,
    SearchPolicy,
    SearchRequest,
    SearchStrategy,
)
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


class PaidFakeProvider(FakeProvider):
    paid = True
    cost_amount = Decimal("1")
    cost_currency = "USD"


def request(limit: int = 2, *, query: str = "стоматология Красноярск") -> SearchRequest:
    return SearchRequest(
        query=query,
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
async def test_parallel_union_calls_every_allowed_provider_and_merges() -> None:
    first = FakeProvider("first", ["https://a.example/", "https://shared.example/"])
    second = FakeProvider("second", ["https://shared.example/?utm_source=y", "https://b.example/"])
    third = FakeProvider("third", ["https://c.example/"])
    gateway = SearchGateway([first, second, third])

    response = await gateway.search(
        request(limit=2),
        SearchPolicy(
            provider_order=("first", "second", "third"),
            strategy=SearchStrategy.PARALLEL_UNION,
            target_results=5,
            max_providers_per_query=3,
        ),
    )

    assert {str(item.url) for item in response.results} == {
        "https://a.example/",
        "https://shared.example/",
        "https://b.example/",
        "https://c.example/",
    }
    assert (first.calls, second.calls, third.calls) == (1, 1, 1)


@pytest.mark.asyncio
async def test_consensus_union_ranks_cross_provider_domain_first() -> None:
    first = FakeProvider("first", ["https://a.example/", "https://shared.example/page-a"])
    second = FakeProvider("second", ["https://shared.example/page-b", "https://b.example/"])
    gateway = SearchGateway([first, second])

    response = await gateway.search(
        request(limit=2),
        SearchPolicy(
            provider_order=("first", "second"),
            strategy=SearchStrategy.CONSENSUS_UNION,
            target_results=4,
            max_providers_per_query=2,
        ),
    )

    assert str(response.results[0].url).startswith("https://shared.example/")
    assert set(response.results[0].corroborated_by) == {"first", "second"}
    assert len(response.results[0].corroborated_by) == 2


@pytest.mark.asyncio
async def test_split_query_routing_assigns_exactly_one_ready_provider_deterministically() -> None:
    providers = [
        FakeProvider("first", ["https://a.example/"]),
        FakeProvider("second", ["https://b.example/"]),
        FakeProvider("third", ["https://c.example/"]),
    ]
    gateway = SearchGateway(providers)
    req = request(query="частная стоматология Красноярск официальный сайт")
    fingerprint = request_fingerprint(req)
    expected = ["first", "second", "third"][int(__import__("hashlib").sha256(fingerprint.encode()).hexdigest()[:8], 16) % 3]

    response = await gateway.search(
        req,
        SearchPolicy(
            provider_order=("first", "second", "third"),
            strategy=SearchStrategy.SPLIT_QUERY_ROUTING,
            max_providers_per_query=3,
        ),
    )

    assert response.diagnostics.selected_provider == expected
    assert sum(provider.calls for provider in providers) == 1
    assert next(provider for provider in providers if provider.name == expected).calls == 1


@pytest.mark.asyncio
async def test_adaptive_strategy_learns_yield_and_reorders_providers() -> None:
    first = FakeProvider("first", [])
    second = FakeProvider("second", ["https://b.example/"])
    gateway = SearchGateway([first, second])

    await gateway.search(
        request(query="train-empty"),
        SearchPolicy(provider_order=("first",), strategy=SearchStrategy.PRIMARY_ONLY, max_providers_per_query=1),
    )
    await gateway.search(
        request(query="train-yield"),
        SearchPolicy(provider_order=("second",), strategy=SearchStrategy.PRIMARY_ONLY, max_providers_per_query=1),
    )

    response = await gateway.search(
        request(query="adaptive-new"),
        SearchPolicy(
            provider_order=("first", "second"),
            strategy=SearchStrategy.ADAPTIVE_COST_QUALITY,
            target_results=1,
            max_providers_per_query=2,
        ),
    )

    assert response.diagnostics.selected_provider == "second"
    assert second.calls == 2
    assert first.calls == 1


@pytest.mark.asyncio
async def test_exhaustive_coverage_ignores_target_and_uses_full_allowed_ceiling() -> None:
    first = FakeProvider("first", ["https://a.example/"])
    second = FakeProvider("second", ["https://b.example/"])
    third = FakeProvider("third", ["https://c.example/"])
    gateway = SearchGateway([first, second, third])

    response = await gateway.search(
        request(limit=1),
        SearchPolicy(
            provider_order=("first", "second", "third"),
            strategy=SearchStrategy.EXHAUSTIVE_COVERAGE,
            target_results=1,
            max_providers_per_query=3,
        ),
    )

    assert {str(item.url) for item in response.results} == {
        "https://a.example/",
        "https://b.example/",
        "https://c.example/",
    }
    assert (first.calls, second.calls, third.calls) == (1, 1, 1)


@pytest.mark.asyncio
async def test_shadow_compare_returns_primary_but_executes_free_secondaries() -> None:
    primary = FakeProvider("primary", ["https://primary.example/"])
    shadow = FakeProvider("shadow", ["https://shadow.example/"])
    gateway = SearchGateway([primary, shadow])

    response = await gateway.search(
        request(),
        SearchPolicy(
            provider_order=("primary", "shadow"),
            strategy=SearchStrategy.SHADOW_COMPARE,
            max_providers_per_query=2,
        ),
    )

    assert [str(item.url) for item in response.results] == ["https://primary.example/"]
    assert response.diagnostics.selected_provider == "primary"
    assert (primary.calls, shadow.calls) == (1, 1)
    assert [attempt.provider for attempt in response.diagnostics.attempts] == ["primary", "shadow"]


@pytest.mark.asyncio
async def test_shadow_compare_does_not_spend_on_paid_secondary_without_fanout_permission() -> None:
    primary = FakeProvider("primary", ["https://primary.example/"])
    paid_shadow = PaidFakeProvider("paid-shadow", ["https://shadow.example/"])
    gateway = SearchGateway([primary, paid_shadow])

    response = await gateway.search(
        request(),
        SearchPolicy(
            provider_order=("primary", "paid-shadow"),
            allowed_providers=frozenset({"primary", "paid-shadow"}),
            strategy=SearchStrategy.SHADOW_COMPARE,
            max_providers_per_query=2,
            allow_paid_fallback=True,
            allow_paid_fanout=False,
            max_cost_by_currency={"USD": Decimal("10")},
        ),
    )

    assert [str(item.url) for item in response.results] == ["https://primary.example/"]
    assert paid_shadow.calls == 0
    assert response.diagnostics.attempts[-1].reason is FallbackReason.POLICY_BLOCKED


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


@pytest.mark.asyncio
async def test_shadow_compare_bypasses_cache_so_benchmark_secondaries_run_each_time() -> None:
    primary = FakeProvider("primary", ["https://primary.example/"])
    shadow = FakeProvider("shadow", ["https://shadow.example/"])
    gateway = SearchGateway([primary, shadow])
    policy = SearchPolicy(
        provider_order=("primary", "shadow"),
        strategy=SearchStrategy.SHADOW_COMPARE,
        max_providers_per_query=2,
    )

    await gateway.search(request(), policy)
    await gateway.search(request(), policy)

    assert (primary.calls, shadow.calls) == (2, 2)
