from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.admin_trace_waterfall_api import router
from app.auth import User, UserRole
from app.auth_api import require_admin
from app.trace_ledger import SQLiteTraceLedger, TraceEventCreate, TraceState


def _app(*, admin: bool = False) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    if admin:
        app.dependency_overrides[require_admin] = lambda: User(
            id=1, username="admin", role=UserRole.ADMIN, is_active=True
        )
    return app


def _append(ledger, *, key, provider, operation, state, reason, counters=None):
    ledger.append(
        TraceEventCreate(
            mission_id="mission-1",
            attempt_id="attempt-1",
            component="search",
            operation=operation,
            state=state,
            reason_code=reason,
            summary=operation,
            provider=provider,
            counters=counters or {},
            event_key=key,
        )
    )


def test_provider_waterfall_requires_admin(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AIMETON_RUNTIME_DB", str(tmp_path / "runtime.sqlite3"))
    response = TestClient(_app()).get(
        "/api/admin/missions/mission-1/trace/attempts/attempt-1/provider-waterfall"
    )
    assert response.status_code in {401, 403}


def test_provider_waterfall_projects_reached_and_missing_stages(monkeypatch, tmp_path) -> None:
    path = tmp_path / "runtime.sqlite3"
    monkeypatch.setenv("AIMETON_RUNTIME_DB", str(path))
    ledger = SQLiteTraceLedger(path)
    _append(ledger, key="1", provider="searxng", operation="provider_selected", state=TraceState.STARTED, reason="selected")
    _append(ledger, key="2", provider="searxng", operation="request_started", state=TraceState.STARTED, reason="called")
    _append(ledger, key="3", provider="searxng", operation="response_received", state=TraceState.SUCCEEDED, reason="returned", counters={"results_received": 4})
    _append(ledger, key="4", provider="tavily", operation="provider_selected", state=TraceState.STARTED, reason="fallback")
    _append(ledger, key="5", provider="tavily", operation="request_started", state=TraceState.FAILED, reason="timeout")

    response = TestClient(_app(admin=True)).get(
        "/api/admin/missions/mission-1/trace/attempts/attempt-1/provider-waterfall"
    )
    assert response.status_code == 200
    payload = response.json()
    assert [item["provider"] for item in payload] == ["searxng", "tavily"]
    assert payload[0]["selected"]["reached"] is True
    assert payload[0]["returned"]["counters"]["results_received"] == 4
    assert payload[0]["accepted"]["reached"] is False
    assert payload[0]["used_in_report"]["reached"] is False
    assert payload[1]["terminal_reason"] == "timeout"
    assert payload[1]["returned"]["reached"] is False


def test_provider_waterfall_missing_provider_trace_is_404(monkeypatch, tmp_path) -> None:
    path = tmp_path / "runtime.sqlite3"
    monkeypatch.setenv("AIMETON_RUNTIME_DB", str(path))
    SQLiteTraceLedger(path)
    response = TestClient(_app(admin=True)).get(
        "/api/admin/missions/mission-1/trace/attempts/missing/provider-waterfall"
    )
    assert response.status_code == 404
    assert response.json()["detail"]["reason"] == "provider_trace_not_found"
