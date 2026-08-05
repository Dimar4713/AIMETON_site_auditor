from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.admin_trace_api import router
from app.auth import User, UserRole
from app.auth_api import require_admin
from app.trace_ledger import SQLiteTraceLedger, TraceEventCreate, TraceState


def _app(*, admin: bool = False) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    if admin:
        app.dependency_overrides[require_admin] = lambda: User(
            id=1,
            username="admin",
            role=UserRole.ADMIN,
            is_active=True,
        )
    return app


def _seed(path) -> None:
    ledger = SQLiteTraceLedger(path)
    ledger.append(
        TraceEventCreate(
            mission_id="mission-1",
            attempt_id="attempt-1",
            component="search",
            operation="provider_selected",
            state=TraceState.STARTED,
            reason_code="selected",
            summary="Provider selected",
            provider="searxng",
            counters={"requested": 1},
            metadata={"authorization": "secret", "query_kind": "company"},
            event_key="event-1",
        )
    )
    ledger.append(
        TraceEventCreate(
            mission_id="mission-1",
            attempt_id="attempt-1",
            component="search",
            operation="response_received",
            state=TraceState.SUCCEEDED,
            reason_code="results_received",
            summary="Results received",
            provider="searxng",
            duration_ms=25,
            counters={"results_received": 2},
            event_key="event-2",
        )
    )


def test_admin_trace_requires_admin(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AIMETON_RUNTIME_DB", str(tmp_path / "runtime.sqlite3"))
    response = TestClient(_app()).get("/api/admin/missions/mission-1/trace/attempts")
    assert response.status_code in {401, 403}


def test_admin_trace_attempts_and_timeline_are_ordered_and_safe(monkeypatch, tmp_path) -> None:
    path = tmp_path / "runtime.sqlite3"
    monkeypatch.setenv("AIMETON_RUNTIME_DB", str(path))
    _seed(path)
    client = TestClient(_app(admin=True))

    attempts = client.get("/api/admin/missions/mission-1/trace/attempts")
    assert attempts.status_code == 200
    assert attempts.json()[0]["attempt_id"] == "attempt-1"
    assert attempts.json()[0]["event_count"] == 2
    assert attempts.json()[0]["terminal_state"] == "succeeded"

    timeline = client.get(
        "/api/admin/missions/mission-1/trace/attempts/attempt-1"
    )
    assert timeline.status_code == 200
    payload = timeline.json()
    assert [event["sequence"] for event in payload] == [1, 2]
    assert payload[0]["metadata"]["authorization"] == "[REDACTED]"
    encoded = timeline.text.lower()
    assert "runtime.sqlite3" not in encoded
    assert '"secret"' not in encoded


def test_admin_trace_jsonl_is_bounded_safe_projection(monkeypatch, tmp_path) -> None:
    path = tmp_path / "runtime.sqlite3"
    monkeypatch.setenv("AIMETON_RUNTIME_DB", str(path))
    _seed(path)
    response = TestClient(_app(admin=True)).get(
        "/api/admin/missions/mission-1/trace/attempts/attempt-1.jsonl?limit=1"
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    lines = response.text.strip().splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["sequence"] == 1
    assert event["metadata"]["authorization"] == "[REDACTED]"


def test_admin_trace_missing_attempt_is_404(monkeypatch, tmp_path) -> None:
    path = tmp_path / "runtime.sqlite3"
    monkeypatch.setenv("AIMETON_RUNTIME_DB", str(path))
    SQLiteTraceLedger(path)
    response = TestClient(_app(admin=True)).get(
        "/api/admin/missions/mission-1/trace/attempts/missing"
    )
    assert response.status_code == 404
    assert response.json()["detail"]["reason"] == "trace_attempt_not_found"
