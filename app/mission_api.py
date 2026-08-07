from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel

from app.auth import User
from app.auth_api import CSRF_COOKIE, CSRF_HEADER, _require_csrf, current_user, require_admin
from app.mission_bounded_runtime import run_owned_site_analysis
from app.mission_contract import (
    Mission,
    MissionCreate,
    MissionRepository,
    MissionState,
    MissionUserProjection,
)
from app.mission_execution import start_mission_execution
from app.mission_observability import derive_runtime_observation
from app.mission_sqlite import SQLiteMissionRepository
from app.models import SiteAnalysis


router = APIRouter(tags=["owned-missions"])


@lru_cache(maxsize=1)
def get_mission_repository() -> MissionRepository:
    return SQLiteMissionRepository()


class MissionStateRequest(BaseModel):
    state: MissionState


class MissionAdminProjection(BaseModel):
    id: str
    owner_id: int
    title: str
    target_ref: str
    state: MissionState
    correlation_id: str

    @classmethod
    def from_mission(cls, mission: Mission) -> "MissionAdminProjection":
        return cls(
            id=mission.id,
            owner_id=mission.owner_id,
            title=mission.title,
            target_ref=mission.target_ref,
            state=mission.state,
            correlation_id=mission.correlation_id,
        )


class MissionEvidenceProjection(BaseModel):
    id: str
    kind: str
    created_at: str
    digest: str | None = None
    data: dict[str, Any]


class MissionUserRecordsProjection(BaseModel):
    mission_id: str
    evidence: list[MissionEvidenceProjection]
    report_metadata: MissionEvidenceProjection | None = None
    report_reason: str | None = None
    last_event_at: str | None = None
    heartbeat_status: str
    stalled: bool
    runtime_reason: str | None = None


_SAFE_FIELDS: dict[str, set[str]] = {
    "turn": {
        "turn_id",
        "status",
        "summary",
        "source_count",
        "completed_at",
        "reason_code",
        "next_action",
    },
    "sufficiency": {"record_id", "level", "status", "summary", "deficits", "updated_at"},
    "report_metadata": {
        "report_id",
        "status",
        "format",
        "content_type",
        "available",
        "release_level",
        "blocked_reason",
        "created_at",
    },
}


def _sanitize_record(record: dict[str, Any]) -> MissionEvidenceProjection:
    kind = str(record.get("kind", ""))
    payload = record.get("payload")
    safe_payload = payload if isinstance(payload, dict) else {}
    allowed = _SAFE_FIELDS.get(kind, set())
    return MissionEvidenceProjection(
        id=str(record.get("id", "")),
        kind=kind,
        created_at=str(record.get("created_at", "")),
        digest=record.get("digest"),
        data={key: safe_payload[key] for key in allowed if key in safe_payload},
    )


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail={"reason": "mission_not_found"})


def _records_for_owner(
    repository: MissionRepository,
    owner_id: int,
    mission_id: str,
) -> list[dict[str, Any]] | None:
    records_reader = getattr(repository, "records_for_owner", None)
    if not callable(records_reader):
        raise HTTPException(status_code=500, detail={"reason": "mission_records_unavailable"})
    return records_reader(owner_id, mission_id)


@router.post(
    "/api/user/missions",
    response_model=MissionUserProjection,
    status_code=status.HTTP_201_CREATED,
)
def create_owned_mission(
    payload: MissionCreate,
    background_tasks: BackgroundTasks,
    user: User = Depends(current_user),
    csrf_cookie: str | None = Cookie(default=None, alias=CSRF_COOKIE),
    csrf_header: str | None = Header(default=None, alias=CSRF_HEADER),
    repository: MissionRepository = Depends(get_mission_repository),
) -> MissionUserProjection:
    _require_csrf(csrf_cookie, csrf_header)
    mission = repository.create(user.id, payload)
    execution = start_mission_execution(
        repository,
        owner_id=user.id,
        mission=mission,
    )
    background_tasks.add_task(
        run_owned_site_analysis,
        repository,
        owner_id=user.id,
        mission=execution.mission,
    )
    return MissionUserProjection.from_mission(execution.mission)


@router.get("/api/user/missions", response_model=list[MissionUserProjection])
def list_owned_missions(
    limit: int = Query(default=100, ge=1, le=1000),
    user: User = Depends(current_user),
    repository: MissionRepository = Depends(get_mission_repository),
) -> list[MissionUserProjection]:
    return [
        MissionUserProjection.from_mission(mission)
        for mission in repository.list_for_owner(user.id, limit)
    ]


@router.get("/api/user/missions/{mission_id}", response_model=MissionUserProjection)
def get_owned_mission(
    mission_id: str,
    user: User = Depends(current_user),
    repository: MissionRepository = Depends(get_mission_repository),
) -> MissionUserProjection:
    mission = repository.get_for_owner(user.id, mission_id)
    if mission is None:
        raise _not_found()
    return MissionUserProjection.from_mission(mission)


@router.get(
    "/api/user/missions/{mission_id}/records",
    response_model=MissionUserRecordsProjection,
)
def get_owned_mission_records(
    mission_id: str,
    user: User = Depends(current_user),
    repository: MissionRepository = Depends(get_mission_repository),
) -> MissionUserRecordsProjection:
    records = _records_for_owner(repository, user.id, mission_id)
    if records is None:
        raise _not_found()
    observation = derive_runtime_observation(records)
    projected = [_sanitize_record(record) for record in records]
    report = next((record for record in reversed(projected) if record.kind == "report_metadata"), None)
    evidence = [record for record in projected if record.kind in {"turn", "sufficiency"}]
    report_reason = None
    if report is None:
        report_reason = "report_not_available"
    elif report.data.get("available") is not True:
        report_reason = str(report.data.get("blocked_reason") or "report_release_blocked")
    return MissionUserRecordsProjection(
        mission_id=mission_id,
        evidence=evidence,
        report_metadata=report,
        report_reason=report_reason,
        last_event_at=observation.last_event_at,
        heartbeat_status=observation.heartbeat_status,
        stalled=observation.stalled,
        runtime_reason=observation.reason_code,
    )


@router.get("/api/user/missions/{mission_id}/report", response_model=SiteAnalysis)
def get_owned_mission_report(
    mission_id: str,
    user: User = Depends(current_user),
    repository: MissionRepository = Depends(get_mission_repository),
) -> SiteAnalysis:
    records = _records_for_owner(repository, user.id, mission_id)
    if records is None:
        raise _not_found()
    report_payload = next(
        (
            record.get("payload")
            for record in reversed(records)
            if record.get("kind") == "report_payload"
        ),
        None,
    )
    if not isinstance(report_payload, dict):
        raise HTTPException(status_code=404, detail={"reason": "report_not_available"})
    return SiteAnalysis.model_validate(report_payload)


@router.patch("/api/user/missions/{mission_id}/state", response_model=MissionUserProjection)
def update_owned_mission_state(
    mission_id: str,
    payload: MissionStateRequest,
    user: User = Depends(current_user),
    csrf_cookie: str | None = Cookie(default=None, alias=CSRF_COOKIE),
    csrf_header: str | None = Header(default=None, alias=CSRF_HEADER),
    repository: MissionRepository = Depends(get_mission_repository),
) -> MissionUserProjection:
    _require_csrf(csrf_cookie, csrf_header)
    mission = repository.update_state_for_owner(user.id, mission_id, payload.state)
    if mission is None:
        raise _not_found()
    return MissionUserProjection.from_mission(mission)


@router.get("/api/admin/missions", response_model=list[MissionAdminProjection])
def admin_list_missions(
    limit: int = Query(default=100, ge=1, le=1000),
    _admin: User = Depends(require_admin),
    repository: MissionRepository = Depends(get_mission_repository),
) -> list[MissionAdminProjection]:
    return [
        MissionAdminProjection.from_mission(mission)
        for mission in repository.list_for_admin(limit)
    ]


@router.get("/api/admin/missions/{mission_id}", response_model=MissionAdminProjection)
def admin_get_mission(
    mission_id: str,
    _admin: User = Depends(require_admin),
    repository: MissionRepository = Depends(get_mission_repository),
) -> MissionAdminProjection:
    mission = repository.get_for_admin(mission_id)
    if mission is None:
        raise _not_found()
    return MissionAdminProjection.from_mission(mission)
