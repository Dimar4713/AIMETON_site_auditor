from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sqlite3
from threading import RLock
from uuid import uuid4

from app.logging_pressure import ModeTransition


class SQLiteLoggingPressureAudit:
    """Durable compact audit ledger for logging mode transitions."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode = WAL")
        return db

    def _migrate(self) -> None:
        with self._lock, self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS logging_pressure_transitions (
                    transition_id TEXT PRIMARY KEY,
                    previous_mode TEXT NOT NULL,
                    current_mode TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    recovery_samples INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_logging_pressure_created
                    ON logging_pressure_transitions(created_at DESC);
                """
            )

    def append(self, transition: ModeTransition) -> str | None:
        if not transition.changed:
            return None
        transition_id = f"logging_pressure_{uuid4().hex}"
        created_at = datetime.now(UTC).isoformat()
        with self._lock, self._connect() as db:
            db.execute(
                """
                INSERT INTO logging_pressure_transitions (
                    transition_id, previous_mode, current_mode, reason,
                    recovery_samples, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    transition_id,
                    transition.previous_mode.value,
                    transition.current_mode.value,
                    transition.reason.value,
                    transition.recovery_samples,
                    created_at,
                ),
            )
        return transition_id

    def latest(self) -> dict[str, object] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM logging_pressure_transitions ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return {
            "transition_id": row["transition_id"],
            "previous_mode": row["previous_mode"],
            "current_mode": row["current_mode"],
            "reason": row["reason"],
            "recovery_samples": row["recovery_samples"],
            "created_at": row["created_at"],
        }
