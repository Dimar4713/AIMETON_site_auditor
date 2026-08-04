from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.trace_ledger import (
    RetentionClass,
    SQLiteTraceLedger,
    TraceEventCreate,
    TraceState,
    sanitize_metadata,
)


def request(**overrides):
    payload = dict(
        mission_id="mission-1",
        attempt_id="attempt-1",
        component="search_gateway",
        operation="provider_request",
        state=TraceState.SUCCEEDED,
        reason_code="results_received",
        summary="Provider returned normalized candidates",
        provider="yandex",
        vertical="official",
        counters={"requested": 1, "results_received": 3, "evidence_accepted": 1},
        metadata={"query_kind": "company_identity", "api_key": "never-store-me"},
        event_key="mission-1:attempt-1:yandex:official:1",
        runtime_version="0.16.3",
    )
    payload.update(overrides)
    return TraceEventCreate(**payload)


def test_trace_is_ordered_idempotent_and_persistent(tmp_path: Path):
    path = tmp_path / "runtime.sqlite3"
    ledger = SQLiteTraceLedger(path)

    first = ledger.append(request())
    duplicate = ledger.append(request())
    second = ledger.append(request(
        event_key="mission-1:attempt-1:yandex:official:2",
        operation="evidence_guard",
        reason_code="accepted",
    ))

    assert duplicate.event_id == first.event_id
    assert first.sequence == 1
    assert second.sequence == 2

    reopened = SQLiteTraceLedger(path)
    events = reopened.list_attempt("mission-1", "attempt-1")
    assert [event.sequence for event in events] == [1, 2]
    assert events[0].metadata["api_key"] == "[REDACTED]"
    assert "never-store-me" not in path.read_bytes().decode("utf-8", errors="ignore")


def test_metadata_is_bounded_and_sensitive_keys_are_redacted():
    safe = sanitize_metadata({
        "authorization": "Bearer secret",
        "cookie": "session=secret",
        "password": "secret",
        "query_kind": "official",
        "large": "x" * 10000,
    })

    assert safe.get("truncated") is True
    assert "digest" in safe
    assert "Bearer secret" not in str(safe)
    assert "session=secret" not in str(safe)


def test_negative_counters_are_rejected():
    try:
        request(counters={"results_received": -1})
    except ValueError as exc:
        assert "non-negative" in str(exc)
    else:
        raise AssertionError("negative counters must fail validation")


def test_retention_defaults_are_persisted(tmp_path: Path):
    ledger = SQLiteTraceLedger(tmp_path / "runtime.sqlite3")
    event = ledger.append(request(retention_class=RetentionClass.DIAGNOSTIC))

    assert event.retention_class is RetentionClass.DIAGNOSTIC
    assert event.policy_version == "logging-retention-v1"
    assert event.retain_until is not None
    assert event.retain_until > event.created_at + timedelta(days=29)

    reopened = SQLiteTraceLedger(tmp_path / "runtime.sqlite3")
    stored = reopened.list_attempt("mission-1", "attempt-1")[0]
    assert stored.retention_class is RetentionClass.DIAGNOSTIC
    assert stored.retain_until == event.retain_until


def test_cleanup_deletes_only_expired_unprotected_events(tmp_path: Path):
    ledger = SQLiteTraceLedger(tmp_path / "runtime.sqlite3")
    now = datetime(2026, 8, 5, tzinfo=UTC)
    expired = now - timedelta(seconds=1)
    future = now + timedelta(days=1)

    ledger.append(request(event_key="expired", retain_until=expired))
    ledger.append(request(event_key="future", retain_until=future))
    ledger.append(request(event_key="frozen", retain_until=expired, frozen=True))
    ledger.append(request(event_key="held", retain_until=expired, legal_hold=True))
    ledger.append(request(event_key="active", mission_id="active-mission", retain_until=expired))

    result = ledger.cleanup_expired(now=now, protected_mission_ids=["active-mission"])

    assert result.deleted == 1
    assert result.protected == 2
    remaining = {
        event.event_key
        for mission_id in ("mission-1", "active-mission")
        for event in ledger.list_attempt(mission_id, "attempt-1")
    }
    assert remaining == {"future", "frozen", "held", "active"}


def test_cleanup_is_bounded_by_batch_size(tmp_path: Path):
    ledger = SQLiteTraceLedger(tmp_path / "runtime.sqlite3")
    now = datetime(2026, 8, 5, tzinfo=UTC)
    for index in range(3):
        ledger.append(request(
            event_key=f"expired-{index}",
            retain_until=now - timedelta(seconds=1),
        ))

    first = ledger.cleanup_expired(now=now, batch_size=2)
    second = ledger.cleanup_expired(now=now, batch_size=2)

    assert first.deleted == 2
    assert second.deleted == 1
