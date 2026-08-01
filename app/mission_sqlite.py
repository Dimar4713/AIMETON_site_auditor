from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from app.mission_contract import Mission, MissionCreate, MissionState, utc_now


MISSION_SCHEMA_VERSION = 1
_ALLOWED_RECORD_KINDS = {"turn", "sufficiency", "report_metadata"}


class SQLiteMissionRepository:
    """SQLite implementation of the canonical MissionRepository boundary."""

    def __init__(self, path: str | Path | None = None):
        configured = path or os.getenv("AIMETON_MISSION_DB", "/app/data/missions.sqlite3")
        self.path = Path(configured)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self.migrate()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def migrate(self) -> None:
        with self._lock, self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS mission_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS missions (
                    id TEXT PRIMARY KEY,
                    owner_id INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_missions_owner_created
                    ON missions(owner_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_missions_correlation
                    ON missions(correlation_id);
                CREATE TABLE IF NOT EXISTS mission_records (
                    id TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    digest TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(mission_id) REFERENCES missions(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_mission_records_mission
                    ON mission_records(mission_id, created_at, id);
                """
            )
            db.execute(
                "INSERT OR REPLACE INTO mission_meta(key, value) VALUES('schema_version', ?)",
                (str(MISSION_SCHEMA_VERSION),),
            )

    @staticmethod
    def _load(payload: str) -> Mission:
        return Mission.model_validate_json(payload)

    @staticmethod
    def _dump(mission: Mission) -> str:
        return mission.model_dump_json()

    def create(self, owner_id: int, request: MissionCreate) -> Mission:
        mission = Mission(owner_id=owner_id, **request.model_dump())
        with self._lock, self._connect() as db:
            db.execute(
                """INSERT INTO missions
                (id, owner_id, state, correlation_id, payload, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    mission.id,
                    mission.owner_id,
                    mission.state.value,
                    mission.correlation_id,
                    self._dump(mission),
                    mission.created_at.isoformat(),
                    mission.updated_at.isoformat(),
                ),
            )
        return mission

    def get_for_owner(self, owner_id: int, mission_id: str) -> Mission | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT payload FROM missions WHERE id = ? AND owner_id = ?",
                (mission_id, owner_id),
            ).fetchone()
        return self._load(row["payload"]) if row else None

    def list_for_owner(self, owner_id: int, limit: int = 100) -> list[Mission]:
        with self._connect() as db:
            rows = db.execute(
                """SELECT payload FROM missions
                WHERE owner_id = ? ORDER BY created_at DESC LIMIT ?""",
                (owner_id, limit),
            ).fetchall()
        return [self._load(row["payload"]) for row in rows]

    def update_state_for_owner(
        self,
        owner_id: int,
        mission_id: str,
        state: MissionState,
    ) -> Mission | None:
        mission = self.get_for_owner(owner_id, mission_id)
        if mission is None:
            return None
        mission.state = state
        mission.updated_at = utc_now()
        with self._lock, self._connect() as db:
            db.execute(
                """UPDATE missions SET state = ?, payload = ?, updated_at = ?
                WHERE id = ? AND owner_id = ?""",
                (
                    mission.state.value,
                    self._dump(mission),
                    mission.updated_at.isoformat(),
                    mission.id,
                    owner_id,
                ),
            )
        return mission

    def get_for_admin(self, mission_id: str) -> Mission | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT payload FROM missions WHERE id = ?",
                (mission_id,),
            ).fetchone()
        return self._load(row["payload"]) if row else None

    def list_for_admin(self, limit: int = 100) -> list[Mission]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT payload FROM missions ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._load(row["payload"]) for row in rows]

    def append_record(
        self,
        mission_id: str,
        kind: str,
        payload: dict[str, Any],
        *,
        digest: str | None = None,
        record_id: str | None = None,
    ) -> str:
        if kind not in _ALLOWED_RECORD_KINDS:
            raise ValueError(f"unsupported mission record kind: {kind}")
        if self.get_for_admin(mission_id) is None:
            raise KeyError(mission_id)
        stable_id = record_id or f"mission_record_{uuid4().hex}"
        with self._lock, self._connect() as db:
            db.execute(
                """INSERT INTO mission_records
                (id, mission_id, kind, payload, digest, created_at)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    stable_id,
                    mission_id,
                    kind,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    digest,
                    utc_now().isoformat(),
                ),
            )
        return stable_id

    def records_for_owner(self, owner_id: int, mission_id: str) -> list[dict[str, Any]] | None:
        if self.get_for_owner(owner_id, mission_id) is None:
            return None
        with self._connect() as db:
            rows = db.execute(
                """SELECT id, kind, payload, digest, created_at FROM mission_records
                WHERE mission_id = ? ORDER BY created_at, id""",
                (mission_id,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "kind": row["kind"],
                "payload": json.loads(row["payload"]),
                "digest": row["digest"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]
