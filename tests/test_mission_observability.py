from datetime import datetime, timezone

import pytest

from app.mission_observability import derive_runtime_observation


def record(*, status: str, created_at: str):
    return {
        "kind": "turn",
        "payload": {"status": status, "summary": "safe"},
        "created_at": created_at,
    }


def test_running_event_is_fresh_within_bound() -> None:
    observed = derive_runtime_observation(
        [record(status="running", created_at="2026-08-03T00:00:00+00:00")],
        now=datetime(2026, 8, 3, 0, 1, tzinfo=timezone.utc),
        stall_after_seconds=90,
    )
    assert observed.heartbeat_status == "fresh"
    assert observed.stalled is False
    assert observed.reason_code is None


def test_running_event_becomes_typed_stalled_after_bound() -> None:
    observed = derive_runtime_observation(
        [record(status="running", created_at="2026-08-03T00:00:00+00:00")],
        now=datetime(2026, 8, 3, 0, 2, tzinfo=timezone.utc),
        stall_after_seconds=90,
    )
    assert observed.heartbeat_status == "stalled"
    assert observed.stalled is True
    assert observed.reason_code == "heartbeat_stalled"


def test_terminal_event_is_not_marked_stalled() -> None:
    observed = derive_runtime_observation(
        [record(status="blocked", created_at="2026-08-02T00:00:00+00:00")],
        now=datetime(2026, 8, 3, 0, 0, tzinfo=timezone.utc),
    )
    assert observed.heartbeat_status == "not_applicable"
    assert observed.stalled is False


def test_missing_valid_timestamp_is_typed_without_guessing() -> None:
    observed = derive_runtime_observation([{"payload": {"status": "running"}}])
    assert observed.heartbeat_status == "missing"
    assert observed.reason_code == "heartbeat_missing"
    assert observed.stalled is False


def test_invalid_bound_is_rejected() -> None:
    with pytest.raises(ValueError):
        derive_runtime_observation([], stall_after_seconds=0)
