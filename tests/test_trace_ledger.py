from pathlib import Path

from app.trace_ledger import SQLiteTraceLedger, TraceEventCreate, TraceState, sanitize_metadata


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
