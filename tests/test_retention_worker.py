from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.retention_worker import RetentionCleanupWorker
from app.trace_ledger import SQLiteTraceLedger, TraceEventCreate, TraceState


def _event(index: int, *, retain_until: datetime, mission_id: str = "mission-1") -> TraceEventCreate:
    return TraceEventCreate(
        mission_id=mission_id,
        attempt_id="attempt-1",
        component="search_gateway",
        operation="provider_request",
        state=TraceState.SUCCEEDED,
        reason_code="results_received",
        event_key=f"event-{index}",
        retain_until=retain_until,
    )


def test_worker_deletes_expired_events_in_bounded_batches(tmp_path: Path):
    now = datetime(2026, 8, 5, tzinfo=UTC)
    ledger = SQLiteTraceLedger(tmp_path / "runtime.sqlite3")
    for index in range(5):
        ledger.append(_event(index, retain_until=now - timedelta(minutes=1)))

    worker = RetentionCleanupWorker(
        ledger,
        batch_size=2,
        max_batches=2,
        max_runtime_seconds=5,
        now=lambda: now,
    )
    summary = worker.run_once()

    assert summary.deleted == 4
    assert summary.batches == 2
    assert summary.stopped_reason == "batch_budget_exhausted"
    assert len(ledger.list_attempt("mission-1", "attempt-1")) == 1


def test_worker_preserves_protected_missions(tmp_path: Path):
    now = datetime(2026, 8, 5, tzinfo=UTC)
    ledger = SQLiteTraceLedger(tmp_path / "runtime.sqlite3")
    ledger.append(_event(1, retain_until=now - timedelta(minutes=1), mission_id="active"))
    ledger.append(_event(2, retain_until=now - timedelta(minutes=1), mission_id="expired"))

    worker = RetentionCleanupWorker(ledger, now=lambda: now)
    summary = worker.run_once(protected_mission_ids={"active"})

    assert summary.deleted == 1
    assert len(ledger.list_attempt("active", "attempt-1")) == 1
    assert ledger.list_attempt("expired", "attempt-1") == []


def test_worker_rejects_unbounded_configuration(tmp_path: Path):
    ledger = SQLiteTraceLedger(tmp_path / "runtime.sqlite3")
    for kwargs in (
        {"batch_size": 0},
        {"max_batches": 0},
        {"max_runtime_seconds": 0},
    ):
        try:
            RetentionCleanupWorker(ledger, **kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError(f"configuration must be rejected: {kwargs}")
