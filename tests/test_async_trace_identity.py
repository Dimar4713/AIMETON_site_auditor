from __future__ import annotations

import pytest

from app.search_gateway.models import SearchPolicy, SearchRequest
from app.search_gateway.traced_gateway import TracedSearchGateway
from app.trace_context import bind_trace_identity, current_trace_identity


@pytest.mark.asyncio
async def test_trace_identity_propagates_to_nested_async_search(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    def capture(_ledger, _diagnostics, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(
        "app.search_gateway.traced_gateway.persist_provider_waterfall",
        capture,
    )
    gateway = TracedSearchGateway([], trace_db_path=tmp_path / "trace.sqlite3")
    request = SearchRequest(
        query="AIMETON",
        mission_id="detached-company-id",
        correlation_id="detached-correlation-id",
    )

    assert current_trace_identity() is None
    with bind_trace_identity("mission-user-visible", "analysis-user-visible"):
        response = await gateway.search(request, SearchPolicy(provider_order=()))
        assert current_trace_identity() is not None

    assert response.diagnostics.state == "unavailable"
    assert captured["mission_id"] == "mission-user-visible"
    assert captured["attempt_id"] == "analysis-user-visible"
    assert current_trace_identity() is None


@pytest.mark.asyncio
async def test_unbound_search_preserves_request_identity(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    def capture(_ledger, _diagnostics, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(
        "app.search_gateway.traced_gateway.persist_provider_waterfall",
        capture,
    )
    gateway = TracedSearchGateway([], trace_db_path=tmp_path / "trace.sqlite3")
    await gateway.search(
        SearchRequest(
            query="AIMETON",
            mission_id="standalone-mission",
            correlation_id="standalone-attempt",
        ),
        SearchPolicy(provider_order=()),
    )

    assert captured["mission_id"] == "standalone-mission"
    assert captured["attempt_id"] == "standalone-attempt"
