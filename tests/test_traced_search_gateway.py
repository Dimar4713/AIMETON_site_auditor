from __future__ import annotations

import httpx
import pytest

from app.search_gateway.models import SearchPolicy, SearchRequest
from app.search_gateway.providers import SearxngProvider
from app.search_gateway.traced_gateway import TracedSearchGateway
from app.trace_ledger import SQLiteTraceLedger


@pytest.mark.asyncio
async def test_gateway_persists_provider_stages_without_query_or_secret(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["q"] == "секретный пользовательский запрос"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "url": "https://example.ru/company",
                        "title": "Example",
                        "content": "Описание компании",
                    }
                ]
            },
        )

    trace_path = tmp_path / "trace.sqlite3"
    gateway = TracedSearchGateway(
        [
            SearxngProvider(
                "https://search.internal",
                transport=httpx.MockTransport(handler),
            )
        ],
        trace_db_path=trace_path,
    )
    request = SearchRequest(
        query="секретный пользовательский запрос",
        limit=5,
        mission_id="mission-live-search",
        correlation_id="attempt-live-search",
    )

    response = await gateway.search(
        request,
        SearchPolicy(provider_order=("searxng",), allowed_providers=frozenset({"searxng"})),
    )

    assert len(response.results) == 1
    events = SQLiteTraceLedger(trace_path).list_attempt(
        "mission-live-search",
        "attempt-live-search",
    )
    assert [event.operation for event in events] == [
        "provider_selected",
        "request_started",
        "response_received",
    ]
    assert all(event.provider == "searxng" for event in events)
    assert events[-1].state.value == "succeeded"
    assert events[-1].counters["results_received"] == 1
    serialized = trace_path.read_bytes().decode("utf-8", errors="ignore").lower()
    assert "секретный пользовательский запрос" not in serialized
    assert "authorization" not in serialized


@pytest.mark.asyncio
async def test_trace_failure_does_not_break_search(tmp_path, monkeypatch):
    provider = SearxngProvider(
        "https://search.internal",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"results": []})
        ),
    )
    gateway = TracedSearchGateway([provider], trace_db_path=tmp_path / "trace.sqlite3")
    monkeypatch.setattr(
        "app.search_gateway.traced_gateway.persist_provider_waterfall",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("trace unavailable")),
    )

    response = await gateway.search(
        SearchRequest(
            query="test",
            limit=5,
            mission_id="mission-fail-open",
            correlation_id="attempt-fail-open",
        ),
        SearchPolicy(provider_order=("searxng",), allowed_providers=frozenset({"searxng"})),
    )

    assert response.results == []
    assert response.diagnostics.attempts[0].state.value == "empty"
