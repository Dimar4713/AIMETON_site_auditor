from __future__ import annotations

from dataclasses import dataclass

from app.logging_pressure import (
    LoggingMode,
    LoggingPressureController,
    ModeTransition,
    ResourceSnapshot,
)
from app.logging_pressure_audit import SQLiteLoggingPressureAudit


@dataclass(frozen=True)
class LoggingPressureStatus:
    mode: LoggingMode
    latest_transition: dict[str, object] | None


class LoggingPressureRuntimeOwner:
    """Single owner for pressure evaluation, transition persistence and status."""

    def __init__(
        self,
        controller: LoggingPressureController,
        audit: SQLiteLoggingPressureAudit,
    ) -> None:
        self.controller = controller
        self.audit = audit

    def evaluate(self, snapshot: ResourceSnapshot) -> ModeTransition:
        transition = self.controller.evaluate(snapshot)
        self.audit.append(transition)
        return transition

    def status(self) -> LoggingPressureStatus:
        return LoggingPressureStatus(
            mode=self.controller.mode,
            latest_transition=self.audit.latest(),
        )
