from __future__ import annotations

from decimal import Decimal

from app.search_gateway.gateway import SearchGateway
from app.search_gateway.models import ProviderReadiness, SearchPolicy, SearchRequest
from app.search_gateway.providers import SearchProvider
from app.search_gateway.scheduler import ScheduledProvider


class DummyProvider(SearchProvider):
    name = "dummy"
    paid = False
    cost_amount = Decimal("0")
    cost_currency = "USD"

    @property
    def configured(self) -> bool:
        return True

    async def search(self, request: SearchRequest, *, timeout_seconds: float):
        return []


def test_scheduled_provider_exposes_bounded_scheduler_policy_in_health() -> None:
    gateway = SearchGateway(
        [
            ScheduledProvider(
                DummyProvider(),
                max_concurrency=2,
                jitter_min_seconds=0.2,
                jitter_max_seconds=0.8,
            )
        ]
    )

    health = gateway.health(SearchPolicy(provider_order=("dummy",)))[0]

    assert health.state is ProviderReadiness.ACTIVE
    assert health.scheduling is not None
    assert health.scheduling.max_concurrency == 2
    assert health.scheduling.jitter_min_seconds == 0.2
    assert health.scheduling.jitter_max_seconds == 0.8


def test_unscheduled_provider_keeps_scheduler_health_optional() -> None:
    gateway = SearchGateway([DummyProvider()])

    health = gateway.health(SearchPolicy(provider_order=("dummy",)))[0]

    assert health.scheduling is None
    dumped = health.model_dump(mode="json", exclude_none=True)
    assert "scheduling" not in dumped


def test_scheduler_health_is_observational_only() -> None:
    provider = ScheduledProvider(
        DummyProvider(),
        max_concurrency=3,
        jitter_min_seconds=0.1,
        jitter_max_seconds=0.4,
    )
    gateway = SearchGateway([provider])
    policy = SearchPolicy(provider_order=("dummy",))

    first = gateway.health(policy)[0].scheduling
    second = gateway.health(policy)[0].scheduling

    assert first == second
    assert first is not None
    assert provider.max_concurrency == 3
