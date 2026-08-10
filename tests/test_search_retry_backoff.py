from __future__ import annotations

from decimal import Decimal

import pytest

from app.search_gateway.factory import search_policy_from_env
from app.search_gateway.gateway import SearchGateway
from app.search_gateway.models import FallbackReason, SearchItem, SearchPolicy, SearchRequest
from app.search_gateway.providers import ProviderError, SearchProvider


class _FlakyProvider(SearchProvider):
    name = "searxng"
    paid = False
    cost_amount = Decimal("0")
    cost_currency = "USD"

    def __init__(
        self,
        *,
        failures: int,
        reason: FallbackReason = FallbackReason.PROVIDER_ERROR,
        retryable: bool = True,
    ) -> None:
        self.failures = failures
        self.reason = reason
        self.retryable = retryable
        self.calls = 0

    @property
    def configured(self) -> bool:
        return True

    async def search(self, request: SearchRequest, *, timeout_seconds: float) -> list[SearchItem]:
        self.calls += 1
        if self.calls <= self.failures:
            raise ProviderError(
                "synthetic provider failure",
                retryable=self.retryable,
                reason=self.reason,
            )
        return [
            SearchItem(
                url="https://example.org/",
                title="Example",
                snippet="Recovered after a bounded retry",
                provider=self.name,
            )
        ]


def _request() -> SearchRequest:
    return SearchRequest(
        query="example company",
        limit=10,
        mission_id="mission-backoff",
        correlation_id="corr-backoff",
    )


def _policy(**updates) -> SearchPolicy:
    policy = SearchPolicy(
        provider_order=("searxng",),
        allowed_providers=frozenset({"searxng"}),
        retries=3,
        retry_backoff_base_seconds=0.5,
        retry_backoff_max_seconds=1.25,
        cache_ttl_seconds=0,
    )
    return policy.model_copy(update=updates)


@pytest.mark.asyncio
async def test_retryable_failures_use_bounded_exponential_backoff() -> None:
    provider = _FlakyProvider(failures=3)
    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    gateway = SearchGateway([provider], sleep=record_sleep)
    response = await gateway.search(_request(), _policy())

    assert provider.calls == 4
    assert delays == [0.5, 1.0, 1.25]
    assert len(response.results) == 1


@pytest.mark.asyncio
async def test_hard_antibot_failure_is_not_retried_or_delayed() -> None:
    provider = _FlakyProvider(
        failures=10,
        reason=FallbackReason.CAPTCHA,
        retryable=False,
    )
    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    gateway = SearchGateway([provider], sleep=record_sleep)
    response = await gateway.search(_request(), _policy())

    assert provider.calls == 1
    assert delays == []
    assert response.diagnostics.attempts[0].reason == FallbackReason.CAPTCHA
    assert gateway.health(_policy())[0].circuit_state == "open"


def test_search_policy_from_env_exposes_retry_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEARCH_RETRY_BACKOFF_BASE_SECONDS", "0.75")
    monkeypatch.setenv("SEARCH_RETRY_BACKOFF_MAX_SECONDS", "6")

    policy = search_policy_from_env()

    assert policy.retry_backoff_base_seconds == 0.75
    assert policy.retry_backoff_max_seconds == 6.0
