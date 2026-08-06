from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.temporal_orchestrator import TrustedTime


class ActivityBlocked(RuntimeError):
    pass


class ActivityConflict(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ActivityEvent:
    event_id: str
    mission_id: str
    agent_id: str
    event_type: str
    state: str
    reason: str
    occurred_at: str
    payload: dict[str, Any]
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class AgentHeartbeat:
    mission_id: str
    agent_id: str
    state: str
    last_seen_at: str
    reason: str
    sequence: int


class AgentActivityRepository:
    """Durable local activity ledger driven only by injected trusted AIMETON time."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS agent_activity_events (
                    event_id TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    state TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE
                );
                CREATE INDEX IF NOT EXISTS idx_agent_activity_mission_time
                    ON agent_activity_events(mission_id, occurred_at, event_id);
                CREATE TABLE IF NOT EXISTS agent_heartbeats (
                    mission_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    PRIMARY KEY (mission_id, agent_id)
                );
                """
            )

    def append_event(
        self,
        *,
        mission_id: str,
        agent_id: str,
        event_type: str,
        state: str,
        reason: str,
        payload: dict[str, Any] | None,
        idempotency_key: str,
        now: TrustedTime,
    ) -> ActivityEvent:
        _require_text(mission_id, agent_id, event_type, state, reason, idempotency_key)
        _require_trusted(now)
        normalized_payload = payload or {}
        payload_json = json.dumps(normalized_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        occurred_at = _iso(now)
        event_id = hashlib.sha256(
            f"{mission_id}\0{agent_id}\0{idempotency_key}".encode("utf-8")
        ).hexdigest()

        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM agent_activity_events WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if row is not None:
                existing = _row_to_event(row)
                if (
                    existing.mission_id != mission_id
                    or existing.agent_id != agent_id
                    or existing.event_type != event_type
                    or existing.state != state
                    or existing.reason != reason
                    or row["payload_hash"] != payload_hash
                ):
                    db.rollback()
                    raise ActivityConflict("idempotency_key_reused_with_different_event")
                db.commit()
                return existing
            db.execute(
                """
                INSERT INTO agent_activity_events(
                    event_id, mission_id, agent_id, event_type, state, reason,
                    occurred_at, payload_json, payload_hash, idempotency_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    mission_id,
                    agent_id,
                    event_type,
                    state,
                    reason,
                    occurred_at,
                    payload_json,
                    payload_hash,
                    idempotency_key,
                ),
            )
            db.commit()
        return ActivityEvent(
            event_id=event_id,
            mission_id=mission_id,
            agent_id=agent_id,
            event_type=event_type,
            state=state,
            reason=reason,
            occurred_at=occurred_at,
            payload=normalized_payload,
            idempotency_key=idempotency_key,
        )

    def heartbeat(
        self,
        *,
        mission_id: str,
        agent_id: str,
        state: str,
        reason: str,
        idempotency_key: str,
        now: TrustedTime,
    ) -> AgentHeartbeat:
        event = self.append_event(
            mission_id=mission_id,
            agent_id=agent_id,
            event_type="heartbeat",
            state=state,
            reason=reason,
            payload={},
            idempotency_key=idempotency_key,
            now=now,
        )
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM agent_heartbeats WHERE mission_id = ? AND agent_id = ?",
                (mission_id, agent_id),
            ).fetchone()
            if row is None:
                sequence = 1
                db.execute(
                    "INSERT INTO agent_heartbeats VALUES (?, ?, ?, ?, ?, ?)",
                    (mission_id, agent_id, state, event.occurred_at, reason, sequence),
                )
            elif row["last_seen_at"] == event.occurred_at and row["state"] == state and row["reason"] == reason:
                sequence = int(row["sequence"])
            else:
                sequence = int(row["sequence"]) + 1
                db.execute(
                    """
                    UPDATE agent_heartbeats
                    SET state = ?, last_seen_at = ?, reason = ?, sequence = ?
                    WHERE mission_id = ? AND agent_id = ?
                    """,
                    (state, event.occurred_at, reason, sequence, mission_id, agent_id),
                )
            db.commit()
        return AgentHeartbeat(mission_id, agent_id, state, event.occurred_at, reason, sequence)

    def latest_heartbeat(self, mission_id: str, agent_id: str) -> AgentHeartbeat | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM agent_heartbeats WHERE mission_id = ? AND agent_id = ?",
                (mission_id, agent_id),
            ).fetchone()
        if row is None:
            return None
        return AgentHeartbeat(
            mission_id=row["mission_id"],
            agent_id=row["agent_id"],
            state=row["state"],
            last_seen_at=row["last_seen_at"],
            reason=row["reason"],
            sequence=int(row["sequence"]),
        )

    def list_events(self, mission_id: str) -> tuple[ActivityEvent, ...]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM agent_activity_events WHERE mission_id = ? ORDER BY occurred_at, event_id",
                (mission_id,),
            ).fetchall()
        return tuple(_row_to_event(row) for row in rows)


def _row_to_event(row: sqlite3.Row) -> ActivityEvent:
    return ActivityEvent(
        event_id=row["event_id"],
        mission_id=row["mission_id"],
        agent_id=row["agent_id"],
        event_type=row["event_type"],
        state=row["state"],
        reason=row["reason"],
        occurred_at=row["occurred_at"],
        payload=json.loads(row["payload_json"]),
        idempotency_key=row["idempotency_key"],
    )


def _require_text(*values: str) -> None:
    if any(not value.strip() for value in values):
        raise ValueError("activity fields must not be empty")


def _require_trusted(now: TrustedTime) -> None:
    if not now.trusted:
        raise ActivityBlocked("blocked:untrusted_time")


def _iso(now: TrustedTime) -> str:
    return now.utc.isoformat().replace("+00:00", "Z")
