from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.admin_mission_retry import AdminMissionRetryService, RetryFailure
from app.auth import User
from app.auth_api import CSRF_COOKIE, CSRF_HEADER, _require_csrf, require_admin
from app.mission_api import MissionAdminProjection, get_mission_repository
from app.mission_sqlite import SQLiteMissionRepository


router = APIRouter(tags=["admin-mission-retry"])


class AdminRetryRequest(BaseModel):
    action: str = Field(min_length=1, max_length=50)
    reason: str = Field(min_length=1, max_length=500)


class AdminMissionEventProjection(BaseModel):
    id: str
    mission_id: str
    actor_id: int
    action: str
    reason: str
    result: str
    created_at: str


def _service(repository=Depends(get_mission_repository)) -> AdminMissionRetryService:
    if not isinstance(repository, SQLiteMissionRepository):
        raise HTTPException(status_code=500, detail={"reason": "mission_retry_repository_unavailable"})
    return AdminMissionRetryService(repository)


@router.post("/api/admin/missions/{mission_id}/retry", response_model=MissionAdminProjection)
def admin_retry_mission(
    mission_id: str,
    payload: AdminRetryRequest,
    admin: User = Depends(require_admin),
    csrf_cookie: str | None = Cookie(default=None, alias=CSRF_COOKIE),
    csrf_header: str | None = Header(default=None, alias=CSRF_HEADER),
    service: AdminMissionRetryService = Depends(_service),
) -> MissionAdminProjection:
    _require_csrf(csrf_cookie, csrf_header)
    decision = service.retry(mission_id, admin, payload.action, payload.reason)
    if decision.failure is RetryFailure.MISSION_NOT_FOUND:
        raise HTTPException(status_code=404, detail={"reason": decision.failure.value})
    if decision.failure is RetryFailure.ACTION_NOT_ALLOWED:
        raise HTTPException(status_code=422, detail={"reason": decision.failure.value})
    if decision.failure is RetryFailure.STATE_NOT_RETRYABLE:
        raise HTTPException(status_code=409, detail={"reason": decision.failure.value})
    assert decision.mission is not None
    return MissionAdminProjection.from_mission(decision.mission)


@router.get("/api/admin/mission-events", response_model=list[AdminMissionEventProjection])
def admin_mission_events(
    limit: int = Query(default=100, ge=1, le=1000),
    _admin: User = Depends(require_admin),
    service: AdminMissionRetryService = Depends(_service),
) -> list[AdminMissionEventProjection]:
    return [AdminMissionEventProjection.model_validate(event) for event in service.list_events(limit)]
