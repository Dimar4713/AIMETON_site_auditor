from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from app.search_gateway.gateway import SearchGateway
from app.search_gateway.models import SearchItem, SearchPolicy, SearchRequest, SearchStrategy
from app.search_gateway.providers import SearchProvider


class _BlockingProvider(SearchProvider):
    name = "searxng"
    paid = False
    cost_amount = Decimal("0")
    cost_currency = "USD"

    def __init__(self) -> None:
        self.calls = 0
        self.started = asyncio.Event()
        self.two_started = asyncio.Event()
        self.release = asyncio.Event()

    @property
    def configured(self) -> bool:
        return True

    async def search(self, request: SearchRequest, *, timeout_seconds: float) -> list[SearchItem]:
        self.calls += 1
        self.started.set()
        if self.calls >= 2:
            self.two_started.set()
        await self.release.wait()
        return [
            SearchItem(
                url="https://example.org/",
                title="Example",
                snippet="One upstream execution can serve concurrent identical callers",
                provider=self.name,
            )
        ]


def _request(*, mission: str, correlation: str, query: str = "example company") -> SearchRequest:
    return SearchRequest(
        query=query,
        limit=10,
        mission_id=mission,
        correlation_id=correlation,
    )


def _policy(strategy: SearchStrategy = SearchStrategy.PRIMARY_ONLY) -> SearchPolicy:
    return SearchPolicy(
        provider_order=("searxng",),
        allowed_providers=frozenset({"searxng"}),
        strategy=strategy,
        retries=0,
        cache_ttl_seconds=0,
    )


@pytest.mark.asyncio
async def test_identical_concurrent_requests_share_one_upstream_execution() -> None:
    provider = _BlockingProvider()
    gateway = SearchGateway([provider])
    policy = _policy()

    owner = asyncio.create_task(
        gateway.search(_request(mission="mission-a", correlation="corr-a"), policy)
    )
    await asyncio.wait_for(provider.started.wait(), timeout=1)

    follower = asyncio.create_task(
        gateway.search(_request(mission="mission-b", correlation="corr-b"), policy)
    )
    await asyncio.sleep(0)
    provider.release.set()

    owner_response, follower_response = await asyncio.gather(owner, follower)

    assert provider.calls == 1
    assert len(owner_response.results) == 1
    assert len(follower_response.results) == 1
    assert owner_response.diagnostics.coalesced is False
    assert follower_response.diagnostics.coalesced is True
    assert follower_response.diagnostics.cache_hit is False
    assert follower_response.diagnostics.total_cost_by_currency == {}
    assert all(attempt.cost_amount == 0 for attempt in follower_response.diagnostics.attempts)


@pytest.mark.asyncio
async def test_different_policy_suffixes_do_not_coalesce() -> None:
    provider = _BlockingProvider()
    gateway = SearchGateway([provider])
    request_a = _request(mission="mission-a", correlation="corr-a")
    request_b = _request(mission="mission-b", correlation="corr-b")

    first = asyncio.create_task(gateway.search(request_a, _policy(SearchStrategy.PRIMARY_ONLY)))
    await asyncio.wait_for(provider.started.wait(), timeout=1)
    second = asyncio.create_task(
        gateway.search(request_b, _policy(SearchStrategy.SEQUENTIAL_UNION))
    )

    await asyncio.wait_for(provider.two_started.wait(), timeout=1)
    provider.release.set()
    first_response, second_response = await asyncio.gather(first, second)

    assert provider.calls == 2
    assert first_response.diagnostics.coalesced is False
    assert second_response.diagnostics.coalesced is False


@pytest.mark.asyncio
async def test_cancelled_follower_does_not_cancel_owner_and_inflight_is_cleaned() -> None:
    provider = _BlockingProvider()
    gateway = SearchGateway([provider])
    policy = _policy()

    owner = asyncio.create_task(
        gateway.search(_request(mission="mission-a", correlation="corr-a"), policy)
    )
    await asyncio.wait_for(provider.started.wait(), timeout=1)
    follower = asyncio.create_task(
        gateway.search(_request(mission="mission-b", correlation="corr-b"), policy)
    )
    await asyncio.sleep(0)

    follower.cancel()
    with pytest.raises(asyncio.CancelledError):
        await follower

    provider.release.set()
    response = await owner
    assert len(response.results) == 1
    assert provider.calls == 1

    # Let the done callback remove the completed in-flight entry. With cache disabled,
    # the next non-overlapping call must perform a fresh provider execution.
    await asyncio.sleep(0)
    second = await gateway.search(
        _request(mission="mission-c", correlation="corr-c"),
        policy,
    )
    assert len(second.results) == 1
    assert provider.calls == 2
