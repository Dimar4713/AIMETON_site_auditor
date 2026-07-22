from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any, TypeVar

from pydantic import BaseModel

from app.runtime_core.models import (
    Event,
    EventCreate,
    Evidence,
    EvidenceCreate,
    PlanStep,
    PlanStepCreate,
    Task,
    TaskCreate,
    TaskState,
    TaskTransition,
    ToolExecution,
    ToolExecutionCreate,
    new_id,
    utc_now,
)

T = TypeVar("T", bound=BaseModel)


SCHEMA_VERSION = 1


class RuntimeStore:
    """Portable persistent Runtime Core store.

    SQLite is the v0.1 baseline because it survives restart/redeploy, requires no
    external service and can later be migrated behind the same store contract.
    """

    def __init__(self, path: str | Path | None = None):
        configured = path or os.getenv("AIMETON_RUNTIME_DB", "data/runtime-core.sqlite3")
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
                CREATE TABLE IF NOT EXISTS runtime_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runtime_tasks (
                    id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    actor_ref TEXT NOT NULL,
                    mandate_ref TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_runtime_tasks_correlation
                    ON runtime_tasks(correlation_id);
                CREATE TABLE IF NOT EXISTS runtime_records (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    actor_ref TEXT NOT NULL,
                    mandate_ref TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES runtime_tasks(id)
                );
                CREATE INDEX IF NOT EXISTS idx_runtime_records_task
                    ON runtime_records(task_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_runtime_records_correlation
                    ON runtime_records(correlation_id);
                """
            )
            db.execute(
                "INSERT OR REPLACE INTO runtime_meta(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

    @staticmethod
    def _json(model: BaseModel) -> str:
        return model.model_dump_json()

    @staticmethod
    def _load(model: type[T], payload: str) -> T:
        return model.model_validate_json(payload)

    def create_task(self, request: TaskCreate) -> Task:
        task = Task(**request.model_dump())
        with self._lock, self._connect() as db:
            db.execute(
                """INSERT INTO runtime_tasks
                (id, state, actor_ref, mandate_ref, correlation_id, payload, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task.id,
                    task.state.value,
                    task.actor_ref,
                    task.mandate_ref,
                    task.correlation_id,
                    self._json(task),
                    task.created_at.isoformat(),
                    task.updated_at.isoformat(),
                ),
            )
        self.append_event(
            task.id,
            EventCreate(
                actor_ref=task.actor_ref,
                mandate_ref=task.mandate_ref,
                event_type="task.created",
                reason="Runtime task registered",
                payload={"state": task.state.value},
                correlation_id=task.correlation_id,
            ),
        )
        return task

    def get_task(self, task_id: str) -> Task | None:
        with self._connect() as db:
            row = db.execute("SELECT payload FROM runtime_tasks WHERE id = ?", (task_id,)).fetchone()
        return self._load(Task, row["payload"]) if row else None

    def list_tasks(self, limit: int = 100) -> list[Task]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT payload FROM runtime_tasks ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._load(Task, row["payload"]) for row in rows]

    def transition_task(self, task_id: str, request: TaskTransition) -> Task:
        task = self.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        previous = task.state
        task.state = request.target_state
        task.updated_at = utc_now()
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE runtime_tasks SET state = ?, payload = ?, updated_at = ? WHERE id = ?",
                (task.state.value, self._json(task), task.updated_at.isoformat(), task.id),
            )
        self.append_event(
            task.id,
            EventCreate(
                actor_ref=request.actor_ref,
                mandate_ref=request.mandate_ref,
                event_type="task.transitioned",
                reason=request.reason,
                payload={"from": previous.value, "to": task.state.value},
                correlation_id=request.correlation_id,
            ),
        )
        return task

    def _append(self, kind: str, record: BaseModel, task_id: str) -> None:
        values = record.model_dump()
        with self._lock, self._connect() as db:
            db.execute(
                """INSERT INTO runtime_records
                (id, task_id, kind, actor_ref, mandate_ref, correlation_id, payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    values["id"],
                    task_id,
                    kind,
                    values["actor_ref"],
                    values["mandate_ref"],
                    values["correlation_id"],
                    record.model_dump_json(),
                    values["created_at"].isoformat(),
                ),
            )

    def append_event(self, task_id: str, request: EventCreate) -> Event:
        self._require_task(task_id)
        record = Event(id=new_id("evt"), task_id=task_id, **request.model_dump())
        self._append("event", record, task_id)
        return record

    def append_evidence(self, task_id: str, request: EvidenceCreate) -> Evidence:
        self._require_task(task_id)
        record = Evidence(id=new_id("evidence"), task_id=task_id, **request.model_dump())
        self._append("evidence", record, task_id)
        return record

    def append_tool_execution(self, task_id: str, request: ToolExecutionCreate) -> ToolExecution:
        self._require_task(task_id)
        record = ToolExecution(id=new_id("toolrun"), task_id=task_id, **request.model_dump())
        self._append("tool_execution", record, task_id)
        return record

    def append_plan_step(self, task_id: str, request: PlanStepCreate) -> PlanStep:
        self._require_task(task_id)
        record = PlanStep(id=new_id("step"), task_id=task_id, **request.model_dump())
        self._append("plan_step", record, task_id)
        return record

    def records(self, task_id: str) -> list[dict[str, Any]]:
        self._require_task(task_id)
        with self._connect() as db:
            rows = db.execute(
                "SELECT kind, payload FROM runtime_records WHERE task_id = ? ORDER BY created_at, id",
                (task_id,),
            ).fetchall()
        return [{"kind": row["kind"], "record": json.loads(row["payload"])} for row in rows]

    def _require_task(self, task_id: str) -> None:
        if self.get_task(task_id) is None:
            raise KeyError(task_id)
