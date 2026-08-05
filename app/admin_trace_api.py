from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from app.auth import User
from app.auth_api import require_admin


router = APIRouter(prefix="/api/admin/missions", tags=["admin-trace"])


class TraceAttemptProjection(BaseModel):
    attempt_id: str
    event_count: int = Field(ge=1)
    first_sequence: int = Field(ge=1)
    last_sequence: int = Field(ge=1)
    started_at: str
    updated_at: str
    terminal_state: str | None = None


class TraceEventProjection(BaseModel):
    event_id: str
    attempt_id: str
    sequence: int = Field(ge=1)
    parent_event_id: str | None = None
    component: str
    operation: str
    state: str
    reason_code: str
    summary: str
    provider: str | None = None
    vertical: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    counters: dict[str, int]
    metadata: dict[str, object]
    metadata_digest: str
    deployed_sha: str | None = None
    runtime_version: str | None = None
    created_at: str


def _db_path() -> Path:
    return Path(os.getenv("AIMETON_RUNTIME_DB", "data/runtime-core.sqlite3"))


def _connect() -> sqlite3.Connection:
    path = _db_path()
    if not path.exists():
        raise HTTPException(status_code=503, detail={"reason": "trace_ledger_unavailable"})
    db = sqlite3.connect(path, timeout=5)
    db.row_factory = sqlite3.Row
    return db


def _event(row: sqlite3.Row) -> TraceEventProjection:
    return TraceEventProjection(
        event_id=row["event_id"],
        attempt_id=row["attempt_id"],
        sequence=row["sequence"],
        parent_event_id=row["parent_event_id"],
        component=row["component"],
        operation=row["operation"],
        state=row["state"],
        reason_code=row["reason_code"],
        summary=row["summary"],
        provider=row["provider"],
        vertical=row["vertical"],
        duration_ms=row["duration_ms"],
        counters=json.loads(row["counters_json"]),
        metadata=json.loads(row["metadata_json"]),
        metadata_digest=row["metadata_digest"],
        deployed_sha=row["deployed_sha"],
        runtime_version=row["runtime_version"],
        created_at=row["created_at"],
    )


@router.get("/{mission_id}/trace/attempts", response_model=list[TraceAttemptProjection])
def list_trace_attempts(
    mission_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    _admin: User = Depends(require_admin),
) -> list[TraceAttemptProjection]:
    with _connect() as db:
        rows = db.execute(
            """
            SELECT attempt_id, COUNT(*) AS event_count,
                   MIN(sequence) AS first_sequence, MAX(sequence) AS last_sequence,
                   MIN(created_at) AS started_at, MAX(created_at) AS updated_at
            FROM mission_trace_events
            WHERE mission_id = ?
            GROUP BY attempt_id
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (mission_id, limit),
        ).fetchall()
        result: list[TraceAttemptProjection] = []
        for row in rows:
            terminal = db.execute(
                """
                SELECT state FROM mission_trace_events
                WHERE mission_id = ? AND attempt_id = ?
                  AND state IN ('succeeded','failed','cancelled','blocked','degraded')
                ORDER BY sequence DESC LIMIT 1
                """,
                (mission_id, row["attempt_id"]),
            ).fetchone()
            result.append(
                TraceAttemptProjection(
                    attempt_id=row["attempt_id"],
                    event_count=row["event_count"],
                    first_sequence=row["first_sequence"],
                    last_sequence=row["last_sequence"],
                    started_at=row["started_at"],
                    updated_at=row["updated_at"],
                    terminal_state=terminal["state"] if terminal else None,
                )
            )
    return result


@router.get("/{mission_id}/trace/attempts/{attempt_id}", response_model=list[TraceEventProjection])
def trace_timeline(
    mission_id: str,
    attempt_id: str,
    limit: int = Query(default=1000, ge=1, le=2000),
    _admin: User = Depends(require_admin),
) -> list[TraceEventProjection]:
    with _connect() as db:
        rows = db.execute(
            """
            SELECT * FROM mission_trace_events
            WHERE mission_id = ? AND attempt_id = ?
            ORDER BY sequence LIMIT ?
            """,
            (mission_id, attempt_id, limit),
        ).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail={"reason": "trace_attempt_not_found"})
    return [_event(row) for row in rows]


@router.get("/{mission_id}/trace/attempts/{attempt_id}.jsonl")
def trace_jsonl_bundle(
    mission_id: str,
    attempt_id: str,
    limit: int = Query(default=1000, ge=1, le=2000),
    _admin: User = Depends(require_admin),
) -> Response:
    events = trace_timeline(mission_id, attempt_id, limit, _admin)
    body = "\n".join(
        json.dumps(event.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
        for event in events
    ) + "\n"
    return Response(
        content=body,
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="trace-{attempt_id}.jsonl"'},
    )
