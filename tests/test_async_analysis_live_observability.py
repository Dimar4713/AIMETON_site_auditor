from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest

import app.analysis_async_api as async_api
from app.search_gateway.models import SearchItem, SearchPolicy, SearchRequest
from app.search_gateway.providers import SearchProvider
from app.search_gateway.traced_gateway import TracedSearchGateway
from app.trace_context import bind_trace_identity


class _BlockingProvider(SearchProvider):
    name = "fake"
    paid = False
    cost_amount = Decimal("0")
    cost_currency = "USD"

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    @property
    def configured(self) -> bool:
        return True

    async def search(
        self,
        request: SearchRequest,
        *,
        timeout_seconds: float,
    ) -> list[SearchItem]:
        self.started.set()
        await self.release.wait()
        return [
            SearchItem(
                url="https://example.com/evidence",
                title="Evidence",
                snippet="bounded result",
                provider=self.name,
            )
        ]


@pytest.mark.asyncio
async def test_live_provider_trace_is_visible_before_provider_returns(tmp_path, monkeypatch):
    trace_path = tmp_path / "trace.sqlite3"
    provider = _BlockingProvider()
    gateway = TracedSearchGateway([provider], trace_db_path=trace_path)
    policy = SearchPolicy(
        provider_order=("fake",),
        allowed_providers=frozenset({"fake"}),
        max_providers_per_query=1,
        retries=0,
        timeout_seconds=5,
    )
    request = SearchRequest(
        query="bounded observability",
        limit=3,
        mission_id="search-internal-id",
        correlation_id="search-correlation",
    )

    monkeypatch.setenv("AIMETON_TRACE_DB", str(trace_path))
    monkeypatch.setattr(async_api, "_canonical_now", lambda: datetime.now(UTC))
    async_api._trace_ledger_for.cache_clear()

    with bind_trace_identity("mission-live", "analysis-live"):
        task = asyncio.create_task(gateway.search(request, policy))
        await asyncio.wait_for(provider.started.wait(), timeout=1)

        in_flight = async_api._trace_runtime_snapshot("mission-live", "analysis-live")
        assert in_flight["queries_planned"] == 1
        assert in_flight["queries_finished"] == 0
        assert in_flight["active_provider_calls"][0]["provider"] == "fake"
        assert in_flight["active_provider_calls"][0]["provider_budget_seconds"] == 5.0

        provider.release.set()
        response = await asyncio.wait_for(task, timeout=1)

    assert len(response.results) == 1
    finished = async_api._trace_runtime_snapshot("mission-live", "analysis-live")
    assert finished["queries_planned"] == 1
    assert finished["queries_finished"] == 1
    assert finished["provider_calls_finished"] == 1
    assert finished["active_provider_calls"] == []


class _FakeReadiness:
    def __init__(self) -> None:
        self.provider_states: dict[str, str] = {}


class _FakeAnalysis:
    def __init__(self) -> None:
        self.readiness = _FakeReadiness()
        self.risks_and_assumptions: list[str] = []


@pytest.mark.asyncio
async def test_bounded_analysis_returns_fallback_on_deadline(monkeypatch):
    async def never_finishes(*args, **kwargs):
        await asyncio.sleep(10)

    fallback = _FakeAnalysis()
    monkeypatch.setattr(async_api, "run_enriched_site_analysis", never_finishes)
    monkeypatch.setattr(async_api, "heuristic_analysis", lambda *args, **kwargs: fallback)
    monkeypatch.setattr(async_api, "_analysis_deadline_seconds", lambda: 0.01)
    monkeypatch.setattr(async_api, "_canonical_now", lambda: datetime.now(UTC))

    async_api._ANALYSES["analysis-deadline"] = {
        "analysis_id": "analysis-deadline",
        "mission_id": "mission-deadline",
        "state": "running",
        "phase": "company_profile_started",
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
        "events": [],
        "result": None,
    }
    try:
        result = await async_api._run_enriched_bounded(
            source_url="https://example.com",
            title="Example",
            text="Example text",
            analysis_id="analysis-deadline",
        )
    finally:
        record = async_api._ANALYSES.pop("analysis-deadline")

    assert result is fallback
    assert fallback.readiness.provider_states["external_enrichment"] == "deadline_exceeded"
    assert any("bounded" in item.lower() for item in fallback.risks_and_assumptions)
    assert record["state"] == "degraded"
    assert record["events"][-1]["event_code"] == "service.degraded"
