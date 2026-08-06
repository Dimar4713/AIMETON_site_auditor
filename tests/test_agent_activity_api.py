from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agent_activity_api import router
from app.runtime_time import RuntimeTimeSnapshot


def snapshot(utc: str, *, trusted: bool = True) -> RuntimeTimeSnapshot:
    return RuntimeTimeSnapshot(
        utc=utc,
        unix_ms=0,
        source="chrony" if trusted else "system_clock",
        synced=trusted,
        offset_ms=0.1 if trusted else None,
        stratum=2 if trusted else None,
        quality="trusted" if trusted else "fallback",
        reason_code=None if trusted else "canonical_status_unavailable",
    )


def client(monkeypatch, tmp_path, utc: str = "2026-08-06T16:00:00.000Z") -> TestClient:
    monkeypatch.setenv("AIMETON_ACTIVITY_DB", str(tmp_path / "activity.sqlite3"))
    monkeypatch.setattr("app.agent_activity_api.runtime_time_snapshot", lambda: snapshot(utc))
    app = FastAPI()
    app.include_router(router, prefix="/api/runtime")
    return TestClient(app)


def test_heartbeat_write_read_and_events(monkeypatch, tmp_path) -> None:
    api = client(monkeypatch, tmp_path)
    payload = {
        "mission_id": "mission-1",
        "agent_id": "agent-a",
        "state": "running",
        "reason": "working",
        "idempotency_key": "hb-1",
    }

    first = api.post("/api/runtime/activity/heartbeat", json=payload)
    repeated = api.post("/api/runtime/activity/heartbeat", json=payload)
    latest = api.get("/api/runtime/activity/missions/mission-1/agents/agent-a/heartbeat")
    events = api.get("/api/runtime/activity/missions/mission-1/events")

    assert first.status_code == 201
    assert repeated.status_code == 201
    assert first.json() == repeated.json()
    assert latest.json()["sequence"] == 1
    assert len(events.json()) == 1


def test_watchdog_classifies_active_stale_blocked_and_unknown(monkeypatch, tmp_path) -> None:
    api = client(monkeypatch, tmp_path, "2026-08-06T16:00:00.000Z")
    api.post(
        "/api/runtime/activity/heartbeat",
        json={
            "mission_id": "mission-1",
            "agent_id": "agent-a",
            "state": "running",
            "reason": "working",
            "idempotency_key": "hb-1",
        },
    )
    active = api.get(
        "/api/runtime/activity/missions/mission-1/agents/agent-a/watchdog",
        params={"stale_after_seconds": 60},
    )
    assert active.json()["status"] == "active"

    monkeypatch.setattr(
        "app.agent_activity_api.runtime_time_snapshot",
        lambda: snapshot("2026-08-06T16:02:00.000Z"),
    )
    stale = api.get(
        "/api/runtime/activity/missions/mission-1/agents/agent-a/watchdog",
        params={"stale_after_seconds": 60},
    )
    assert stale.json()["status"] == "stale"

    api.post(
        "/api/runtime/activity/heartbeat",
        json={
            "mission_id": "mission-1",
            "agent_id": "agent-b",
            "state": "blocked",
            "reason": "owner_decision_required",
            "idempotency_key": "hb-2",
        },
    )
    blocked = api.get(
        "/api/runtime/activity/missions/mission-1/agents/agent-b/watchdog",
        params={"stale_after_seconds": 60},
    )
    unknown = api.get(
        "/api/runtime/activity/missions/mission-1/agents/missing/watchdog",
        params={"stale_after_seconds": 60},
    )
    assert blocked.json()["status"] == "blocked"
    assert unknown.json()["status"] == "unknown"


def test_untrusted_time_and_conflict_fail_closed(monkeypatch, tmp_path) -> None:
    api = client(monkeypatch, tmp_path)
    payload = {
        "mission_id": "mission-1",
        "agent_id": "agent-a",
        "state": "running",
        "reason": "working",
        "idempotency_key": "same",
    }
    assert api.post("/api/runtime/activity/heartbeat", json=payload).status_code == 201
    conflict = dict(payload, state="blocked", reason="different")
    assert api.post("/api/runtime/activity/heartbeat", json=conflict).status_code == 409

    monkeypatch.setattr(
        "app.agent_activity_api.runtime_time_snapshot",
        lambda: snapshot("2026-08-06T16:01:00.000Z", trusted=False),
    )
    blocked = api.post(
        "/api/runtime/activity/heartbeat",
        json=dict(payload, idempotency_key="new"),
    )
    watchdog = api.get(
        "/api/runtime/activity/missions/mission-1/agents/agent-a/watchdog"
    )
    assert blocked.status_code == 503
    assert watchdog.status_code == 503
