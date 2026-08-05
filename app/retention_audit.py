from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3
from threading import RLock
from uuid import uuid4

from app.retention_worker import RetentionRunSummary


class SQLiteRetentionAuditLedger:
    """Durable compact audit ledger for retention cleanup runs."""

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
                CREATE TABLE IF NOT EXISTS retention_cleanup_runs (
                    run_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL,
                    batches INTEGER NOT NULL,
                    deleted INTEGER NOT NULL,
                    protected INTEGER NOT NULL,
                    stopped_reason TEXT NOT NULL,
                    summary_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_retention_cleanup_finished
                    ON retention_cleanup_runs(finished_at DESC);
                """
            )

    def append(self, summary: RetentionRunSummary) -> str:
        if summary.deleted < 0 or summary.protected < 0 or summary.batches < 0:
            raise ValueError("retention audit counters must be non-negative")
        run_id = f"retention_{uuid4().hex}"
        payload = asdict(summary)
        payload["started_at"] = summary.started_at.isoformat()
        payload["finished_at"] = summary.finished_at.isoformat()
        created_at = datetime.now(UTC).isoformat()
        with self._lock, self._connect() as db:
            db.execute(
                """
                INSERT INTO retention_cleanup_runs (
                    run_id, started_at, finished_at, batches, deleted, protected,
                    stopped_reason, summary_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    summary.started_at.isoformat(),
                    summary.finished_at.isoformat(),
                    summary.batches,
                    summary.deleted,
                    summary.protected,
                    summary.stopped_reason,
                    json.dumps(payload, sort_keys=True),
                    created_at,
                ),
            )
        return run_id

    def latest(self) -> dict[str, object] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM retention_cleanup_runs ORDER BY finished_at DESC, created_at DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return {
            "run_id": row["run_id"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "batches": row["batches"],
            "deleted": row["deleted"],
            "protected": row["protected"],
            "stopped_reason": row["stopped_reason"],
        }
