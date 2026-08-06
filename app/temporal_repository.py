from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from app.temporal_orchestrator import TemporalIntent, TimeoutAction


class IdempotencyConflict(ValueError):
    pass


class VersionConflict(ValueError):
    pass


class TemporalIntentRepository:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS temporal_intents (
                    wait_id TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    payload_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    version INTEGER NOT NULL
                )
                """
            )

    def create(self, intent: TemporalIntent, *, idempotency_key: str, status: str = "scheduled") -> TemporalIntent:
        payload = _serialize_intent(intent)
        payload_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        with self._connect() as db:
            row = db.execute(
                "SELECT payload_hash, payload_json FROM temporal_intents WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if row:
                if row["payload_hash"] != payload_hash:
                    raise IdempotencyConflict("idempotency key reused with different payload")
                return _deserialize_intent(row["payload_json"])
            db.execute(
                "INSERT INTO temporal_intents(wait_id, mission_id, idempotency_key, payload_hash, payload_json, status, version) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (intent.wait_id, intent.mission_id, idempotency_key, payload_hash, payload, status, intent.version),
            )
        return intent

    def get(self, wait_id: str) -> TemporalIntent | None:
        with self._connect() as db:
            row = db.execute("SELECT payload_json FROM temporal_intents WHERE wait_id = ?", (wait_id,)).fetchone()
        return None if row is None else _deserialize_intent(row["payload_json"])

    def update_status(self, wait_id: str, *, status: str, expected_version: int) -> int:
        with self._connect() as db:
            cursor = db.execute(
                "UPDATE temporal_intents SET status = ?, version = version + 1 WHERE wait_id = ? AND version = ?",
                (status, wait_id, expected_version),
            )
            if cursor.rowcount != 1:
                raise VersionConflict("stale or missing temporal intent")
            row = db.execute("SELECT version FROM temporal_intents WHERE wait_id = ?", (wait_id,)).fetchone()
        return int(row["version"])


def _serialize_intent(intent: TemporalIntent) -> str:
    data = asdict(intent)
    for key in ("created_at", "resume_not_before", "deadline"):
        data[key] = data[key].isoformat().replace("+00:00", "Z")
    data["timeout_action"] = intent.timeout_action.value
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def _deserialize_intent(payload: str) -> TemporalIntent:
    data = json.loads(payload)
    for key in ("created_at", "resume_not_before", "deadline"):
        data[key] = datetime.fromisoformat(data[key].replace("Z", "+00:00"))
    data["timeout_action"] = TimeoutAction(data["timeout_action"])
    return TemporalIntent(**data)
