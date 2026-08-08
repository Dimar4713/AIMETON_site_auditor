from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from app.search_gateway.models import SearchItem, SearchRequest
from app.search_gateway.providers import SearchProvider
from app.search_gateway.scheduler import ScheduledProvider


class ProbeProvider(SearchProvider):
    name = "probe"
    paid = False
    cost_amount = Decimal("0")
    cost_currency = "USD"

    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self.release = asyncio.Event()

    @property
    def configured(self) -> bool:
        return True

    async def search(self, request: SearchRequest, *, timeout_seconds: float) -> list[SearchItem]:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await self.release.wait()
            return [SearchItem(url=f"https://example.test/{request.correlation_id}", provider=self.name)]
        finally:
            self.active -= 1


def _request(index: int) -> SearchRequest:
    return SearchRequest(
        query=f"query {index}",
        mission_id="mission-scheduler",
        correlation_id=f"corr-{index}",
    )


@pytest.mark.asyncio
async def test_scheduler_enforces_provider_local_concurrency():
    provider = ProbeProvider()
    scheduled = ScheduledProvider(provider, max_concurrency=2)

    tasks = [asyncio.create_task(scheduled.search(_request(index), timeout_seconds=1)) for index in range(5)]
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert provider.max_active == 2
    provider.release.set()
    await asyncio.gather(*tasks)
    assert provider.max_active == 2


@pytest.mark.asyncio
async def test_scheduler_applies_bounded_observable_jitter_before_provider_call():
    delays: list[float] = []

    async def fake_sleep(value: float) -> None:
        delays.append(value)

    class ImmediateProvider(SearchProvider):
        name = "immediate"
        paid = False
        cost_amount = Decimal("0")
        cost_currency = "USD"

        @property
        def configured(self) -> bool:
            return True

        async def search(self, request: SearchRequest, *, timeout_seconds: float) -> list[SearchItem]:
            return []

    scheduled = ScheduledProvider(
        ImmediateProvider(),
        max_concurrency=1,
        jitter_min_seconds=0.2,
        jitter_max_seconds=0.8,
        sleep=fake_sleep,
        jitter=lambda low, high: (low + high) / 2,
    )

    await scheduled.search(_request(1), timeout_seconds=1)

    assert delays == [0.5]
    assert 0.2 <= delays[0] <= 0.8


def test_scheduler_rejects_invalid_limits():
    class ImmediateProvider(SearchProvider):
        name = "immediate"
        paid = False
        cost_amount = Decimal("0")
        cost_currency = "USD"

        @property
        def configured(self) -> bool:
            return True

        async def search(self, request: SearchRequest, *, timeout_seconds: float) -> list[SearchItem]:
            return []

    with pytest.raises(ValueError):
        ScheduledProvider(ImmediateProvider(), max_concurrency=0)
    with pytest.raises(ValueError):
        ScheduledProvider(ImmediateProvider(), jitter_min_seconds=1, jitter_max_seconds=0.5)
