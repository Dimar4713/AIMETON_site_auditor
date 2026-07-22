from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class TaskState(StrEnum):
    CREATED = "created"
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    VALIDATION = "validation"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RuntimeRecord(BaseModel):
    id: str
    task_id: str
    actor_ref: str
    mandate_ref: str
    correlation_id: str
    reason: str = Field(min_length=1, max_length=1000)
    created_at: datetime = Field(default_factory=utc_now)


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    actor_ref: str = Field(min_length=1, max_length=200)
    mandate_ref: str = Field(min_length=1, max_length=200)
    commitment: str = Field(min_length=1, max_length=2000)
    completion_criteria: list[str] = Field(min_length=1)
    external_refs: dict[str, str] = Field(default_factory=dict)
    correlation_id: str = Field(default_factory=lambda: new_id("corr"))


class Task(TaskCreate):
    id: str = Field(default_factory=lambda: new_id("task"))
    state: TaskState = TaskState.CREATED
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class TaskTransition(BaseModel):
    actor_ref: str
    mandate_ref: str
    target_state: TaskState
    reason: str = Field(min_length=1, max_length=1000)
    correlation_id: str


class EventCreate(BaseModel):
    actor_ref: str
    mandate_ref: str
    event_type: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=1000)
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str


class Event(RuntimeRecord):
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)


class EvidenceCreate(BaseModel):
    actor_ref: str
    mandate_ref: str
    evidence_type: str = Field(min_length=1, max_length=200)
    source_ref: str = Field(min_length=1, max_length=1000)
    reason: str = Field(min_length=1, max_length=1000)
    summary: str = Field(min_length=1, max_length=4000)
    digest: str | None = Field(default=None, max_length=200)
    correlation_id: str


class Evidence(RuntimeRecord):
    evidence_type: str
    source_ref: str
    summary: str
    digest: str | None = None


class ToolExecutionCreate(BaseModel):
    actor_ref: str
    mandate_ref: str
    tool_ref: str = Field(min_length=1, max_length=300)
    operation: str = Field(min_length=1, max_length=300)
    reason: str = Field(min_length=1, max_length=1000)
    result_status: str = Field(min_length=1, max_length=100)
    evidence_ids: list[str] = Field(default_factory=list)
    correlation_id: str


class ToolExecution(RuntimeRecord):
    tool_ref: str
    operation: str
    result_status: str
    evidence_ids: list[str] = Field(default_factory=list)


class PlanStepCreate(BaseModel):
    actor_ref: str
    mandate_ref: str
    title: str = Field(min_length=1, max_length=300)
    ordinal: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=1000)
    result_status: str = "pending"
    correlation_id: str


class PlanStep(RuntimeRecord):
    title: str
    ordinal: int
    result_status: str
