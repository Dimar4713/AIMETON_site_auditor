from __future__ import annotations

import pytest

from app.evidence_crawler import search_discovery
from app.search_gateway.models import (
    GatewayState,
    SearchDiagnostics,
    SearchItem,
    SearchResponse,
)


class StubGateway:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def search(self, request, policy):
        self.queries.append(request.query)
        if "реквизиты" in request.query:
            results = [
                SearchItem(
                    url="https://www.example.ru/company/details",
                    title="Реквизиты",
                    provider="searxng",
                ),
                SearchItem(
                    url="https://evil.example.net/copied-details",
                    title="Копия реквизитов",
                    provider="searxng",
                ),
            ]
        elif "контакты" in request.query:
            results = [
                SearchItem(
                    url="https://example.ru/contacts",
                    title="Контакты",
                    provider="searxng",
                )
            ]
        else:
            results = []
        return SearchResponse(
            results=results,
            diagnostics=SearchDiagnostics(
                state=GatewayState.SUCCESS,
                selected_provider="searxng",
            ),
        )


def test_same_host_family_accepts_www_equivalence_only():
    assert search_discovery.same_host_family(
        "https://example.ru/",
        "https://www.example.ru/about",
    )
    assert not search_discovery.same_host_family(
        "https://example.ru/",
        "https://example.ru.attacker.test/about",
    )
    assert not search_discovery.same_host_family(
        "https://example.ru/",
        "https://other.example.ru/about",
    )


@pytest.mark.asyncio
async def test_discovery_returns_only_same_domain_and_prioritizes_identity_pages(monkeypatch):
    gateway = StubGateway()
    monkeypatch.setattr(search_discovery, "get_search_gateway", lambda: gateway)
    monkeypatch.setattr(search_discovery, "search_policy_from_env", lambda: object())

    result = await search_discovery.discover_same_domain_urls(
        "https://example.ru/",
        company_name='ООО "Пример"',
        mission_id="mission-same-domain",
        correlation_id="corr-same-domain",
    )

    assert result.urls == (
        "https://www.example.ru/company/details",
        "https://example.ru/contacts",
    )
    assert len(gateway.queries) == len(search_discovery.DISCOVERY_TOPICS)
    assert all(query.startswith("site:example.ru") for query in gateway.queries)
    assert result.diagnostics.state == GatewayState.SUCCESS


@pytest.mark.asyncio
async def test_invalid_root_fails_closed_without_outbound_search(monkeypatch):
    class ExplodingGateway:
        async def search(self, request, policy):
            raise AssertionError("search must not run")

    monkeypatch.setattr(search_discovery, "get_search_gateway", lambda: ExplodingGateway())

    result = await search_discovery.discover_same_domain_urls(
        "not-a-url",
        company_name=None,
        mission_id="mission-invalid-root",
        correlation_id="corr-invalid-root",
    )

    assert result.urls == ()
    assert result.diagnostics.state == GatewayState.UNAVAILABLE
