from app.logging_pressure import (
    LoggingMode,
    ModeTransition,
    PressureReason,
)
from app.logging_pressure_audit import SQLiteLoggingPressureAudit


def test_changed_transition_is_persisted_and_survives_reopen(tmp_path) -> None:
    path = tmp_path / "runtime.sqlite3"
    audit = SQLiteLoggingPressureAudit(path)
    transition = ModeTransition(
        previous_mode=LoggingMode.FULL,
        current_mode=LoggingMode.THROTTLED,
        reason=PressureReason.QUEUE_PRESSURE,
        changed=True,
        recovery_samples=0,
    )
    transition_id = audit.append(transition)
    assert transition_id is not None

    latest = SQLiteLoggingPressureAudit(path).latest()
    assert latest is not None
    assert latest["transition_id"] == transition_id
    assert latest["previous_mode"] == "full"
    assert latest["current_mode"] == "throttled"
    assert latest["reason"] == "queue_pressure"
    assert latest["recovery_samples"] == 0


def test_unchanged_evaluation_does_not_create_audit_noise(tmp_path) -> None:
    audit = SQLiteLoggingPressureAudit(tmp_path / "runtime.sqlite3")
    transition = ModeTransition(
        previous_mode=LoggingMode.FULL,
        current_mode=LoggingMode.FULL,
        reason=PressureReason.NONE,
        changed=False,
        recovery_samples=0,
    )
    assert audit.append(transition) is None
    assert audit.latest() is None
