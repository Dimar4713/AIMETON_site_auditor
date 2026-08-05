from app.logging_pressure import (
    LoggingMode,
    LoggingPressureController,
    PressureReason,
    ResourceSnapshot,
)
from app.logging_pressure_audit import SQLiteLoggingPressureAudit
from app.logging_pressure_runtime import LoggingPressureRuntimeOwner


def test_runtime_owner_evaluates_persists_and_projects_status(tmp_path) -> None:
    path = tmp_path / "runtime.sqlite3"
    owner = LoggingPressureRuntimeOwner(
        LoggingPressureController(),
        SQLiteLoggingPressureAudit(path),
    )

    transition = owner.evaluate(ResourceSnapshot(queue_depth=5_000))
    assert transition.current_mode is LoggingMode.THROTTLED
    assert transition.reason is PressureReason.QUEUE_PRESSURE

    status = owner.status()
    assert status.mode is LoggingMode.THROTTLED
    assert status.latest_transition is not None
    assert status.latest_transition["current_mode"] == "throttled"
    assert status.latest_transition["reason"] == "queue_pressure"


def test_runtime_owner_does_not_persist_unchanged_samples(tmp_path) -> None:
    owner = LoggingPressureRuntimeOwner(
        LoggingPressureController(),
        SQLiteLoggingPressureAudit(tmp_path / "runtime.sqlite3"),
    )
    transition = owner.evaluate(ResourceSnapshot())
    assert transition.changed is False
    assert owner.status().mode is LoggingMode.FULL
    assert owner.status().latest_transition is None
