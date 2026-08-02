from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from app.auth import User
from app.mission_contract import Mission, MissionState
from app.mission_sqlite import SQLiteMissionRepository


class RetryAction(StrEnum):
    RESUME = "resume"


class RetryFailure(StrEnum):
    MISSION_NOT_FOUND = "mission_not_found"
    ACTION_NOT_ALLOWED = "retry_action_not_allowed"
    STATE_NOT_RETRYABLE = "mission_state_not_retryable"


@dataclass(frozen=True)
class RetryDecision:
    mission: Mission | None
    failure: RetryFailure | None = None


class AdminMissionRetryService:
    _ALLOWED_ACTIONS = {RetryAction.RESUME}
    _RETRYABLE_STATES = {MissionState.BLOCKED, MissionState.DEGRADED}

    def __init__(self, repository: SQLiteMissionRepository):
        self.repository = repository
        self._initialize_audit(repository.path)

    @staticmethod
    def _initialize_audit(path: Path) -> None:
        with sqlite3.connect(path) as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS mission_admin_events (
                    id TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    actor_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    result TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_mission_admin_events_mission ON mission_admin_events(mission_id, created_at)"
            )

    def _audit(self, mission_id: str, actor: User, action: str, reason: str, result: str) -> None:
        with sqlite3.connect(self.repository.path) as db:
            db.execute(
                """INSERT INTO mission_admin_events
                (id, mission_id, actor_id, action, reason, result, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    f"mission_admin_event_{uuid4().hex}",
                    mission_id,
                    actor.id,
                    action,
                    reason.strip()[:500],
                    result,
                    datetime.now(UTC).isoformat(),
                ),
            )

    def retry(self, mission_id: str, actor: User, action: str, reason: str) -> RetryDecision:
        if action not in self._ALLOWED_ACTIONS:
            self._audit(mission_id, actor, action, reason, RetryFailure.ACTION_NOT_ALLOWED.value)
            return RetryDecision(None, RetryFailure.ACTION_NOT_ALLOWED)
        mission = self.repository.get_for_admin(mission_id)
        if mission is None:
            self._audit(mission_id, actor, action, reason, RetryFailure.MISSION_NOT_FOUND.value)
            return RetryDecision(None, RetryFailure.MISSION_NOT_FOUND)
        if mission.state not in self._RETRYABLE_STATES:
            self._audit(mission_id, actor, action, reason, RetryFailure.STATE_NOT_RETRYABLE.value)
            return RetryDecision(None, RetryFailure.STATE_NOT_RETRYABLE)
        updated = self.repository.update_state_for_owner(mission.owner_id, mission.id, MissionState.RUNNING)
        assert updated is not None
        self._audit(mission_id, actor, action, reason, "success")
        return RetryDecision(updated)

    def list_events(self, limit: int = 100) -> list[dict[str, object]]:
        with sqlite3.connect(self.repository.path) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                """SELECT id, mission_id, actor_id, action, reason, result, created_at
                FROM mission_admin_events ORDER BY created_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
