from pathlib import Path

from app.logging_pressure import LoggingMode, LoggingPressureController, PressurePolicy
from app.logging_pressure_audit import SQLiteLoggingPressureAudit
from app.logging_pressure_runtime import LoggingPressureRuntimeOwner, LoggingPressureStatus


def test_stage_acceptance_uses_typed_pressure_status(tmp_path: Path) -> None:
    owner = LoggingPressureRuntimeOwner(
        LoggingPressureController(policy=PressurePolicy(recovery_samples=1)),
        SQLiteLoggingPressureAudit(tmp_path / "pressure.sqlite3"),
    )

    status = owner.status()

    assert isinstance(status, LoggingPressureStatus)
    assert status.mode is LoggingMode.FULL
    assert status.latest_transition is None
