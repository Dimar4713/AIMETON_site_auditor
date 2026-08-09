from __future__ import annotations

from pathlib import Path

import pytest

from app import discovery
from app.models import HuntRequest
from app.search_gateway.models import GatewayState, SearchDiagnostics, SearchItem, SearchResponse
from app.trace_ledger import RetentionClass, SQLiteTraceLedger


class FakeGateway:
    async def search(self, request, _policy):
        return SearchResponse(
            results=[
                SearchItem(
                    url="https://2gis.ru/krasnoyarsk/search/dentistry",
                    title="Стоматологии Красноярска",
                    snippet="Каталог организаций",
                    provider="fake",
                ),
                SearchItem(
                    url="https://clinic.ru/",
                    title="Стоматология Красноярск",
                    snippet="Лечение зубов и имплантация",
                    provider="fake",
                ),
                SearchItem(
                    url="https://clinic.ru/services",
                    title="Стоматология Красноярск — услуги",
                    snippet="Лечение зубов",
                    provider="fake",
                ),
                SearchItem(
                    url="https://dentist2.ru/",
                    title="Стоматологическая клиника Красноярск",
                    snippet="Имплантация и лечение зубов",
                    provider="fake",
                ),
                SearchItem(
                    url="https://irrelevant.ru/",
                    title="Новости Красноярска",
                    snippet="Городской информационный портал",
                    provider="fake",
                ),
            ],
            diagnostics=SearchDiagnostics(
                state=GatewayState.SUCCESS,
                selected_provider="fake",
            ),
        )


@pytest.mark.asyncio
async def test_hunter_forensic_trace_explains_candidate_losses(tmp_path: Path, monkeypatch):
    trace_path = tmp_path / "runtime.sqlite3"
    monkeypatch.setenv("AIMETON_RUNTIME_DB", str(trace_path))
    monkeypatch.setattr(discovery, "get_search_gateway", lambda: FakeGateway())

    async def no_llm_plan(**_kwargs):
        return None

    async def fake_fetch(url: str):
        return {
            "final_url": url,
            "title": "Стоматология Красноярск",
            "text": "Красноярск стоматология лечение зубов имплантация запись услуги " * 40,
        }

    monkeypatch.setattr(discovery, "generate_hunter_query_plan", no_llm_plan)
    monkeypatch.setattr(discovery, "_build_queries", lambda _req: ["стоматология Красноярск"])
    monkeypatch.setattr(discovery, "fetch_site", fake_fetch)

    result = await discovery.run_hunt(
        HuntRequest(
            region="Красноярск",
            industries=["стоматология"],
            max_queries=1,
            results_per_query=10,
            max_candidates=10,
            minimum_pre_score=55,
            deep_audit_score=70,
            output_limit=1,
            concurrency=2,
        )
    )

    assert len(result.candidates) == 1

    with SQLiteTraceLedger(trace_path)._connect() as db:
        row = db.execute(
            "SELECT mission_id, attempt_id FROM mission_trace_events WHERE component = 'hunter' ORDER BY sequence LIMIT 1"
        ).fetchone()
    assert row is not None
    events = SQLiteTraceLedger(trace_path).list_attempt(row["mission_id"], row["attempt_id"])
    hunter_events = [event for event in events if event.component == "hunter"]
    operations = [event.operation for event in hunter_events]

    assert "hunt_plan" in operations
    assert "candidate_excluded" in operations
    assert "candidate_deduplicated" in operations
    assert "candidate_dedupe_retained" in operations
    assert "candidate_pre_scored" in operations
    assert "candidate_rejected" in operations
    assert "candidate_deep_audit_started" in operations
    assert "candidate_deep_audit_completed" in operations
    assert "candidate_returned" in operations
    assert "candidate_output_omitted" in operations
    assert operations[-1] == "hunt_funnel_complete"
    assert all(event.retention_class is RetentionClass.FORENSIC for event in hunter_events)

    excluded = next(event for event in hunter_events if event.reason_code == "excluded_host")
    assert excluded.metadata["candidate_host"] == "2gis.ru"

    duplicate = next(event for event in hunter_events if event.reason_code == "duplicate_domain")
    assert duplicate.metadata["candidate_host"] == "clinic.ru"

    rejected = next(event for event in hunter_events if event.reason_code == "below_minimum_pre_score")
    assert rejected.metadata["candidate_url"] == "https://irrelevant.ru/"
    assert rejected.counters["pre_score"] < rejected.counters["minimum_pre_score"]

    final = hunter_events[-1]
    assert final.counters == {
        "raw_results": 5,
        "excluded_results": 1,
        "duplicate_results": 1,
        "pool_omitted_results": 0,
        "unique_candidates": 3,
        "inspected_candidates": 3,
        "qualified_candidates": 2,
        "returned_candidates": 1,
        "output_omitted_candidates": 1,
    }


def test_hunter_forensic_trace_is_bounded_and_sanitized(tmp_path: Path, monkeypatch):
    from app.hunter_forensic_trace import HunterForensicTrace
    from app.trace_ledger import TraceState

    path = tmp_path / "trace.sqlite3"
    trace = HunterForensicTrace("hunt-test", "attempt-test", trace_db_path=path)
    trace.append(
        "candidate_test",
        state=TraceState.SUCCEEDED,
        reason_code="test",
        summary="test",
        url="https://example.ru/path?utm_source=secret#fragment",
        title="Clinic",
        metadata={
            "authorization": "must-not-survive",
            "api_key": "must-not-survive",
            "safe_reason": "diagnostic",
        },
    )

    event = SQLiteTraceLedger(path).list_attempt("hunt-test", "attempt-test")[0]
    assert event.retention_class is RetentionClass.FORENSIC
    assert event.metadata["candidate_url"] == "https://example.ru/path"
    assert event.metadata["authorization"] == "[REDACTED]"
    assert event.metadata["api_key"] == "[REDACTED]"
    assert event.metadata["safe_reason"] == "diagnostic"
