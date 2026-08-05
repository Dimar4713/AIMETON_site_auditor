from __future__ import annotations

from app.trace_ledger import TraceEventCreate, TraceState
from app.trace_write_metrics import (
    InstrumentedSQLiteTraceLedger,
    TraceWriteMetrics,
    trace_pressure_callbacks,
)


def _event(index: int) -> TraceEventCreate:
    return TraceEventCreate(
        mission_id="mission-1",
        attempt_id="attempt-1",
        component="test",
        operation="append",
        state=TraceState.SUCCEEDED,
        reason_code="test",
        event_key=f"event-{index}",
    )


def test_metrics_track_pending_and_bounded_latency() -> None:
    metrics = TraceWriteMetrics(latency_window=20)
    metrics.begin()
    assert metrics.queue_depth() == 1
    metrics.finish(12.5)
    assert metrics.queue_depth() == 0
    assert metrics.write_p95_ms() == 12.5


def test_instrumented_ledger_publishes_real_write_latency(tmp_path) -> None:
    path = tmp_path / "runtime.sqlite3"
    ledger = InstrumentedSQLiteTraceLedger(path)
    queue_depth, write_p95_ms = trace_pressure_callbacks(path)

    assert queue_depth() == 0
    assert write_p95_ms() == 0.0

    ledger.append(_event(1))

    assert queue_depth() == 0
    assert write_p95_ms() >= 0.0


def test_registry_is_shared_for_same_runtime_db(tmp_path) -> None:
    path = tmp_path / "runtime.sqlite3"
    first = InstrumentedSQLiteTraceLedger(path)
    second = InstrumentedSQLiteTraceLedger(path)
    queue_depth, write_p95_ms = trace_pressure_callbacks(path)

    first.append(_event(1))
    second.append(_event(2))

    assert queue_depth() == 0
    assert write_p95_ms() >= 0.0
