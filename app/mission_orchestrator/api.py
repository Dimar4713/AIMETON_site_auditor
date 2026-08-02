from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from app.admin_mission_retry_api import router as admin_mission_retry_router
from app.admin_workspace_api import router as admin_workspace_router
from app.mission_api import router as ownership_router
from app.mission_orchestrator.models import (
    ActionCandidate,
    ActionOutcome,
    EntryPoint,
    MissionCreateRequest,
    MissionSnapshot,
    NextActionPlan,
    PolicySnapshot,
    SufficiencyFeedback,
)
from app.mission_orchestrator.service import get_mission_orchestrator
from app.workspace_api import router as workspace_router


router = APIRouter()
legacy_router = APIRouter(prefix="/api/missions", tags=["mission-orchestrator"])


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlanRequest(ApiModel):
    deficits: list[str]
    candidates: list[ActionCandidate]
    policy: PolicySnapshot


class RecordTurnRequest(ApiModel):
    plan: NextActionPlan
    outcome: ActionOutcome
    feedback: SufficiencyFeedback


@legacy_router.post("", response_model=MissionSnapshot)
def create_mission(request: MissionCreateRequest):
    try:
        return get_mission_orchestrator().create_mission(
            request,
            entry_point=EntryPoint.REST,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@legacy_router.get("/{mission_id}", response_model=MissionSnapshot)
def get_mission(mission_id: str):
    try:
        return get_mission_orchestrator().get(mission_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="mission_not_found") from exc


@legacy_router.post("/{mission_id}/plan", response_model=NextActionPlan)
def plan_next_action(mission_id: str, request: PlanRequest):
    try:
        return get_mission_orchestrator().plan(
            mission_id,
            deficits=request.deficits,
            candidates=request.candidates,
            policy=request.policy,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="mission_not_found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@legacy_router.post("/{mission_id}/turns", response_model=MissionSnapshot)
def record_turn(mission_id: str, request: RecordTurnRequest):
    try:
        return get_mission_orchestrator().record_turn(
            mission_id,
            plan=request.plan,
            outcome=request.outcome,
            feedback=request.feedback,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="mission_not_found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


router.include_router(legacy_router)
router.include_router(ownership_router)
router.include_router(workspace_router)
router.include_router(admin_workspace_router)
router.include_router(admin_mission_retry_router)
