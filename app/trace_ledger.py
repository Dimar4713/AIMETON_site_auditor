from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from threading import RLock
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


MAX_SUMMARY_LENGTH = 500
MAX_METADATA_BYTES = 4096
_SECRET_KEY = re.compile(r"(api[_-]?key|authorization|cookie|password|secret|token|prompt|chain[_-]?of[_-]?thought)", re.I)


class TraceState(StrEnum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    DEGRADED = "degraded"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class TraceEventCreate(BaseModel):
    mission_id: str = Field(min_length=1, max_length=128)
    attempt_id: str = Field(min_length=1, max_length=128)
    component: str = Field(min_length=1, max_length=128)
    operation: str = Field(min_length=1, max_length=128)
    state: TraceState
    reason_code: str = Field(min_length=1, max_length=128)
    summary: str = Field(default="", max_length=MAX_SUMMARY_LENGTH)
    provider: str | None = Field(default=None, max_length=128)
    vertical: str | None = Field(default=None, max_length=128)
    parent_event_id: str | None = Field(default=None, max_length=128)
    duration_ms: int | None = Field(default=None, ge=0)
    counters: dict[str, int] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    event_key: str = Field(min_length=1, max_length=256)
    deployed_sha: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    runtime_version: str | None = Field(default=None, max_length=64)

    @field_validator("counters")
    @classmethod
    def counters_are_non_negative(cls, value: dict[str, int]) -> dict[str, int]:
        if any(not isinstance(item, int) or item < 0 for item in value.values()):
            raise ValueError("trace counters must be non-negative integers")
        return value


class TraceEvent(TraceEventCreate):
    event_id: str
    sequence: int
    created_at: datetime
    metadata_digest: str


def sanitize_metadata(value: dict[str, Any]) -> dict[str, Any]:
    """Return an allow-safe bounded projection, never raw secrets or payloads."""
    cleaned: dict[str, Any] = {}
    for key, item in value.items():
        if _SECRET_KEY.search(str(key)):
            cleaned[str(key)] = "[REDACTED]"
            continue
        if isinstance(item, (str, int, float, bool)) or item is None:
            cleaned[str(key)] = item if not isinstance(item, str) else item[:500]
        elif isinstance(item, list):
            cleaned[str(key)] = [str(entry)[:200] for entry in item[:20]]
        else:
            cleaned[str(key)] = str(item)[:500]
    encoded = json.dumps(cleaned, ensure_ascii=False, sort_keys=True).encode("utf-8")
    if len(encoded) > MAX_METADATA_BYTES:
        return {"truncated": True, "digest": hashlib.sha256(encoded).hexdigest()}
    return cleaned


class SQLiteTraceLedger:
    """Append-only, idempotent and restart-safe technological trace ledger."""

    def __init__(self, path: str | Path):
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
                CREATE TABLE IF NOT EXISTS mission_trace_events (
                    event_id TEXT PRIMARY KEY,
                    event_key TEXT NOT NULL UNIQUE,
                    mission_id TEXT NOT NULL,
                    attempt_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    parent_event_id TEXT,
                    component TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    state TEXT NOT NULL,
                    reason_code TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    provider TEXT,
                    vertical TEXT,
                    duration_ms INTEGER,
                    counters_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    metadata_digest TEXT NOT NULL,
                    deployed_sha TEXT,
                    runtime_version TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(mission_id, attempt_id, sequence)
                );
                CREATE INDEX IF NOT EXISTS idx_trace_mission_attempt
                    ON mission_trace_events(mission_id, attempt_id, sequence);
                """
            )

    def append(self, request: TraceEventCreate) -> TraceEvent:
        safe_metadata = sanitize_metadata(request.metadata)
        metadata_json = json.dumps(safe_metadata, ensure_ascii=False, sort_keys=True)
        metadata_digest = hashlib.sha256(metadata_json.encode("utf-8")).hexdigest()
        with self._lock, self._connect() as db:
            existing = db.execute(
                "SELECT * FROM mission_trace_events WHERE event_key = ?", (request.event_key,)
            ).fetchone()
            if existing:
                return self._row(existing)
            row = db.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence FROM mission_trace_events WHERE mission_id = ? AND attempt_id = ?",
                (request.mission_id, request.attempt_id),
            ).fetchone()
            sequence = int(row["next_sequence"])
            event_id = f"trace_{uuid4().hex}"
            created_at = datetime.now(UTC)
            db.execute(
                """
                INSERT INTO mission_trace_events (
                    event_id, event_key, mission_id, attempt_id, sequence, parent_event_id,
                    component, operation, state, reason_code, summary, provider, vertical,
                    duration_ms, counters_json, metadata_json, metadata_digest,
                    deployed_sha, runtime_version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id, request.event_key, request.mission_id, request.attempt_id,
                    sequence, request.parent_event_id, request.component, request.operation,
                    request.state.value, request.reason_code, request.summary, request.provider,
                    request.vertical, request.duration_ms,
                    json.dumps(request.counters, sort_keys=True), metadata_json, metadata_digest,
                    request.deployed_sha, request.runtime_version, created_at.isoformat(),
                ),
            )
        return TraceEvent(
            **request.model_dump(), event_id=event_id, sequence=sequence,
            created_at=created_at, metadata=safe_metadata, metadata_digest=metadata_digest,
        )

    def list_attempt(self, mission_id: str, attempt_id: str) -> list[TraceEvent]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM mission_trace_events WHERE mission_id = ? AND attempt_id = ? ORDER BY sequence",
                (mission_id, attempt_id),
            ).fetchall()
        return [self._row(row) for row in rows]

    @staticmethod
    def _row(row: sqlite3.Row) -> TraceEvent:
        return TraceEvent(
            event_id=row["event_id"], event_key=row["event_key"], mission_id=row["mission_id"],
            attempt_id=row["attempt_id"], sequence=row["sequence"], parent_event_id=row["parent_event_id"],
            component=row["component"], operation=row["operation"], state=TraceState(row["state"]),
            reason_code=row["reason_code"], summary=row["summary"], provider=row["provider"],
            vertical=row["vertical"], duration_ms=row["duration_ms"],
            counters=json.loads(row["counters_json"]), metadata=json.loads(row["metadata_json"]),
            metadata_digest=row["metadata_digest"], deployed_sha=row["deployed_sha"],
            runtime_version=row["runtime_version"], created_at=datetime.fromisoformat(row["created_at"]),
        )
