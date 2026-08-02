from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_mission_id() -> str:
    return f"mission_{uuid4().hex}"


class MissionState(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    DEGRADED = "degraded"
    BLOCKED = "blocked"
    COMPLETED = "completed"


class MissionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    target_ref: str = Field(min_length=1, max_length=1000)
    input_snapshot: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str = Field(min_length=1, max_length=200)


class Mission(BaseModel):
    id: str = Field(default_factory=new_mission_id)
    owner_id: int
    title: str
    target_ref: str
    state: MissionState = MissionState.CREATED
    input_snapshot: dict[str, Any] = Field(default_factory=dict)
    technical_snapshot: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class MissionUserProjection(BaseModel):
    id: str
    title: str
    target_ref: str
    state: MissionState
    correlation_id: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_mission(cls, mission: Mission) -> "MissionUserProjection":
        return cls(
            id=mission.id,
            title=mission.title,
            target_ref=mission.target_ref,
            state=mission.state,
            correlation_id=mission.correlation_id,
            created_at=mission.created_at,
            updated_at=mission.updated_at,
        )


@runtime_checkable
class MissionRepository(Protocol):
    """Replaceable persistence boundary for canonical missions.

    The authenticated actor supplies owner_id server-side. Client payloads never
    choose or override ownership.
    """

    def create(self, owner_id: int, request: MissionCreate) -> Mission: ...

    def get_for_owner(self, owner_id: int, mission_id: str) -> Mission | None: ...

    def list_for_owner(self, owner_id: int, limit: int = 100) -> list[Mission]: ...

    def update_state_for_owner(
        self,
        owner_id: int,
        mission_id: str,
        state: MissionState,
    ) -> Mission | None: ...

    def get_for_admin(self, mission_id: str) -> Mission | None: ...

    def list_for_admin(self, limit: int = 100) -> list[Mission]: ...
