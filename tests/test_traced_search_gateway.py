from __future__ import annotations

import json

import httpx
import pytest

from app.search_gateway.models import SearchPolicy, SearchRequest
from app.search_gateway.providers import SearxngProvider
from app.search_gateway.traced_gateway import TracedSearchGateway
from app.trace_ledger import SQLiteTraceLedger


@pytest.mark.asyncio
async def test_gateway_persists_bounded_query_and_provider_stages_without_secret_transport_data(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["q"] == "диагностический пользовательский запрос"
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
        query="диагностический пользовательский запрос",
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
        "query_planned",
        "provider_selected",
        "request_started",
        "response_received",
        "normalized",
    ]
    assert events[0].provider is None
    assert events[0].metadata["query_text"] == "диагностический пользовательский запрос"
    assert events[0].counters == {"requested_limit": 5}
    assert all(event.provider == "searxng" for event in events[1:])
    assert events[-1].state.value == "succeeded"
    assert events[-1].reason_code == "search_items_normalized"
    assert events[-1].counters == {
        "results_received": 1,
        "results_normalized": 1,
    }

    projected = json.dumps(
        [
            {
                "summary": event.summary,
                "metadata": event.metadata,
                "counters": event.counters,
            }
            for event in events
        ],
        ensure_ascii=False,
    ).lower()
    assert "диагностический пользовательский запрос" in projected
    for forbidden in ("authorization", "api_key", "password", "cookie", "raw_payload"):
        assert forbidden not in projected


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
