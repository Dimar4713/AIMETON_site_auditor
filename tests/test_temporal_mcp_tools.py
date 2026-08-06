from datetime import datetime, timedelta, timezone

from app.runtime_time import RuntimeTimeSnapshot
from app.temporal_mcp_tools import deadline_check_payload, wait_status_payload
from app.temporal_orchestrator import TemporalIntent
from app.temporal_repository import TemporalIntentRepository


def _intent(now: datetime) -> TemporalIntent:
    return TemporalIntent(
        wait_id="wait-1",
        mission_id="mission-1",
        created_at=now,
        resume_not_before=now + timedelta(minutes=5),
        deadline=now + timedelta(minutes=20),
    )


def _snapshot(now: datetime, *, trusted: bool = True) -> RuntimeTimeSnapshot:
    return RuntimeTimeSnapshot(
        utc=now.isoformat().replace("+00:00", "Z"),
        unix_ms=int(now.timestamp() * 1000),
        source="chrony" if trusted else "system_clock",
        synced=trusted,
        offset_ms=0.1 if trusted else None,
        stratum=2 if trusted else None,
        quality="trusted" if trusted else "fallback",
        reason_code=None if trusted else "canonical_status_unavailable",
    )


def test_wait_status_is_read_only_and_reports_not_found(tmp_path):
    repository = TemporalIntentRepository(tmp_path / "temporal.sqlite3")
    assert wait_status_payload("missing", repository=repository) == {
        "wait_id": "missing",
        "found": False,
        "status": "not_found",
        "read_only": True,
    }
    assert repository.get("missing") is None


def test_wait_status_returns_persisted_intent(tmp_path):
    now = datetime(2026, 8, 6, 13, 0, tzinfo=timezone.utc)
    repository = TemporalIntentRepository(tmp_path / "temporal.sqlite3")
    repository.create(_intent(now), idempotency_key="key-1")

    payload = wait_status_payload("wait-1", repository=repository)

    assert payload["found"] is True
    assert payload["read_only"] is True
    assert payload["intent"]["resume_not_before"].endswith("Z")


def test_deadline_check_uses_supplied_trusted_time(tmp_path):
    now = datetime(2026, 8, 6, 13, 0, tzinfo=timezone.utc)
    repository = TemporalIntentRepository(tmp_path / "temporal.sqlite3")
    repository.create(_intent(now), idempotency_key="key-1")

    waiting = deadline_check_payload(
        "wait-1",
        repository=repository,
        snapshot=_snapshot(now + timedelta(minutes=1)),
    )
    ready = deadline_check_payload(
        "wait-1",
        repository=repository,
        snapshot=_snapshot(now + timedelta(minutes=6)),
    )
    timed_out = deadline_check_payload(
        "wait-1",
        repository=repository,
        snapshot=_snapshot(now + timedelta(minutes=20)),
    )

    assert waiting["state"] == "waiting"
    assert ready["state"] == "ready"
    assert timed_out["state"] == "timed_out"
    assert all(payload["read_only"] for payload in (waiting, ready, timed_out))


def test_deadline_check_fails_closed_for_untrusted_time(tmp_path):
    now = datetime(2026, 8, 6, 13, 0, tzinfo=timezone.utc)
    repository = TemporalIntentRepository(tmp_path / "temporal.sqlite3")
    repository.create(_intent(now), idempotency_key="key-1")

    payload = deadline_check_payload(
        "wait-1",
        repository=repository,
        snapshot=_snapshot(now, trusted=False),
    )

    assert payload["state"] == "blocked"
    assert payload["reason"] == "blocked:untrusted_time"


def test_deadline_check_missing_intent_does_not_create_record(tmp_path):
    repository = TemporalIntentRepository(tmp_path / "temporal.sqlite3")

    payload = deadline_check_payload("missing", repository=repository)

    assert payload["state"] == "blocked"
    assert payload["reason"] == "blocked:intent_not_found"
    assert repository.get("missing") is None
