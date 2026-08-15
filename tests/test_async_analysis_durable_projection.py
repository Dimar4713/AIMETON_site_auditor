from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

import app.analysis_async_api as async_api
from app.analysis_runtime_projection import AnalysisRuntimeProjectionStore
from app.mission_orchestrator import EntryPoint
from app.runtime_core.storage import RuntimeStore


def _configure_projection(monkeypatch, tmp_path, instance_id: str) -> str:
    path = tmp_path / "runtime-core.sqlite3"
    monkeypatch.setenv("AIMETON_RUNTIME_DB", str(path))
    monkeypatch.setenv("AIMETON_TRACE_DB", str(path))
    monkeypatch.setattr(async_api, "runtime_instance_id", lambda: instance_id)
    monkeypatch.setattr(async_api, "_canonical_now", lambda: datetime.now(UTC))
    async_api._analysis_projection_for.cache_clear()
    async_api._trace_ledger_for.cache_clear()
    return str(path)


def test_projection_store_coexists_with_runtime_core_and_roundtrips(tmp_path):
    path = tmp_path / "runtime-core.sqlite3"
    RuntimeStore(path)
    store = AnalysisRuntimeProjectionStore(path)
    store.upsert(
        analysis_id="analysis-1",
        mission_id="mission-1",
        source_url="https://example.com",
        state="running",
        phase="company_profile_started",
        created_at="2026-08-15T13:00:00+00:00",
        updated_at="2026-08-15T13:00:01+00:00",
        runtime_instance_id="a" * 32,
        result=None,
    )
    event = {
        "sequence": 1,
        "timestamp": "2026-08-15T13:00:01Z",
        "phase": "company_profile_started",
        "event_code": "picture.assembled",
        "icon": "🧩",
        "state": "running",
        "icon_key": "building",
        "message": "running",
        "detail": None,
        "heartbeat": True,
        "next_action": "continue",
    }
    store.append_event("analysis-1", event)

    projection = store.get("analysis-1")
    assert projection is not None
    assert projection.mission_id == "mission-1"
    assert projection.source_url == "https://example.com"
    assert projection.state == "running"
    assert projection.runtime_instance_id == "a" * 32
    assert store.events("analysis-1") == [event]

    with sqlite3.connect(path) as db:
        tables = {
            row[0]
            for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    assert "runtime_tasks" in tables
    assert "runtime_records" in tables
    assert "runtime_analysis_projection" in tables
    assert "runtime_analysis_events" in tables


def test_nonterminal_analysis_survives_restart_as_explicit_interruption(monkeypatch, tmp_path):
    path = _configure_projection(monkeypatch, tmp_path, "a" * 32)
    started = async_api.create_analysis_runtime(
        "https://example.com",
        entry_point=EntryPoint.MCP,
    )
    original_events = async_api.get_analysis_events_payload(started.analysis_id)
    assert original_events[0]["event_code"] == "mission.received"

    async_api._ANALYSES.pop(started.analysis_id)
    monkeypatch.setattr(async_api, "runtime_instance_id", lambda: "b" * 32)
    async_api._analysis_projection_for.cache_clear()
    async_api._trace_ledger_for.cache_clear()

    status = async_api.get_analysis_status_payload(started.analysis_id)
    events = async_api.get_analysis_events_payload(started.analysis_id)

    assert status["analysis_id"] == started.analysis_id
    assert status["mission_id"] == started.mission_id
    assert status["state"] == "stalled"
    assert status["phase"] == "runtime_restart_detected"
    assert status["interrupted_by_runtime_restart"] is True
    assert status["interruption_reason"] == "runtime_instance_changed"
    assert status["previous_state"] == "queued"
    assert status["resume_required"] is True
    assert status["resume_supported"] is False
    assert status["result"] is None
    assert events[:-1] == original_events
    assert events[-1]["phase"] == "runtime_restart_detected"
    assert events[-1]["event_code"] == "flow.gap_detected"
    assert events[-1]["state"] == "stalled"
    assert "controlled resume" in (events[-1]["next_action"] or "").lower()

    # Reading the interrupted state must not mutate durable history.
    store = AnalysisRuntimeProjectionStore(path)
    assert store.events(started.analysis_id) == original_events


def test_terminal_analysis_remains_terminal_after_runtime_instance_change(monkeypatch, tmp_path):
    path = _configure_projection(monkeypatch, tmp_path, "c" * 32)
    store = AnalysisRuntimeProjectionStore(path)
    result = {"analysis_id": "analysis-terminal", "summary": "done"}
    store.upsert(
        analysis_id="analysis-terminal",
        mission_id="mission-terminal",
        source_url="https://example.com",
        state="completed",
        phase="completed",
        created_at="2026-08-15T13:00:00+00:00",
        updated_at="2026-08-15T13:01:00+00:00",
        runtime_instance_id="c" * 32,
        result=result,
    )
    store.append_event(
        "analysis-terminal",
        {
            "sequence": 1,
            "timestamp": "2026-08-15T13:01:00Z",
            "phase": "completed",
            "event_code": "mission.completed",
            "icon": "✅",
            "state": "completed",
            "icon_key": "check-circle",
            "message": "done",
            "detail": None,
            "heartbeat": False,
            "next_action": None,
        },
    )
    monkeypatch.setattr(async_api, "runtime_instance_id", lambda: "d" * 32)
    async_api._ANALYSES.pop("analysis-terminal", None)
    async_api._analysis_projection_for.cache_clear()
    async_api._trace_ledger_for.cache_clear()

    status = async_api.get_analysis_status_payload("analysis-terminal")
    events = async_api.get_analysis_events_payload("analysis-terminal")

    assert status["state"] == "completed"
    assert status["phase"] == "completed"
    assert status["result"] == result
    assert status["interrupted_by_runtime_restart"] is False
    assert status["resume_required"] is False
    assert events[-1]["event_code"] == "mission.completed"
    assert len(events) == 1


def test_interrupted_progress_never_claims_dead_provider_or_llm_activity():
    progress = {
        "queries_planned": 17,
        "queries_finished": 12,
        "provider_calls_finished": 18,
        "provider_failures": 2,
        "active_provider_calls": [
            {"provider": "yandex", "query_index": 42, "elapsed_seconds": 8.0}
        ],
        "llm_state": "running",
        "llm_provider": "routerai",
        "llm_elapsed_seconds": 20.0,
        "llm_budget_seconds": 60.0,
        "llm_overdue": False,
    }

    projected = async_api._interrupted_progress(progress)

    assert projected["active_provider_calls"] == []
    assert projected["interrupted_active_provider_calls"] == 1
    assert projected["llm_state"] == "interrupted"
    assert projected["llm_overdue"] is False
    assert projected["queries_planned"] == 17
    assert projected["queries_finished"] == 12
