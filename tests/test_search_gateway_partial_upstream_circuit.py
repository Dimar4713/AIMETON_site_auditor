from __future__ import annotations

from decimal import Decimal

import pytest

from app.search_gateway.models import FallbackReason
from app.search_gateway.providers import (
    ProviderDegradation,
    SearchProvider,
    SearxngProvider,
)
from app.search_gateway.traced_gateway import TracedSearchGateway


class _SingleUpstreamProvider(SearchProvider):
    name = "single"
    paid = False
    cost_amount = Decimal("0")
    cost_currency = "USD"

    @property
    def configured(self) -> bool:
        return True

    async def search(self, request, *, timeout_seconds: float):
        return []


@pytest.mark.asyncio
async def test_partial_searxng_captcha_does_not_open_provider_circuit(tmp_path) -> None:
    provider = SearxngProvider(
        "http://searxng.test",
        engines=("brave", "duckduckgo", "bing"),
        engine_fanout=2,
    )
    provider._record_degradation(
        ProviderDegradation(
            reason=FallbackReason.CAPTCHA,
            upstreams=("brave", "duckduckgo"),
        )
    )
    gateway = TracedSearchGateway(
        [provider],
        trace_db_path=tmp_path / "trace.sqlite3",
    )

    await gateway._record_failure("searxng", FallbackReason.CAPTCHA)

    assert gateway._circuit_state("searxng") == "closed"
    assert [row.upstream for row in provider.upstream_cooldowns()] == [
        "brave",
        "duckduckgo",
    ]
    assert provider.upstream_circuit_open() is False


@pytest.mark.asyncio
async def test_all_searxng_engines_cooling_still_open_provider_circuit(tmp_path) -> None:
    provider = SearxngProvider(
        "http://searxng.test",
        engines=("brave", "duckduckgo"),
        engine_fanout=2,
    )
    provider._record_degradation(
        ProviderDegradation(
            reason=FallbackReason.CAPTCHA,
            upstreams=("brave", "duckduckgo"),
        )
    )
    gateway = TracedSearchGateway(
        [provider],
        trace_db_path=tmp_path / "trace.sqlite3",
    )

    await gateway._record_failure("searxng", FallbackReason.CAPTCHA)

    assert provider.upstream_circuit_open() is True
    assert gateway._circuit_state("searxng") == "open"


@pytest.mark.asyncio
async def test_single_upstream_hard_failure_keeps_existing_immediate_open(tmp_path) -> None:
    gateway = TracedSearchGateway(
        [_SingleUpstreamProvider()],
        trace_db_path=tmp_path / "trace.sqlite3",
    )

    await gateway._record_failure("single", FallbackReason.CAPTCHA)

    assert gateway._circuit_state("single") == "open"
