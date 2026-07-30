from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.entity_resolution.factory import get_entity_resolver
from app.entity_resolution.models import (
    IdentityResolutionHistory,
    IdentityResolutionResult,
)
from app.entity_resolution.registry_api import router as registry_router
from app.evidence_crawler.models import BootstrapCrawlResult
from app.mission_orchestrator import (
    NextActionPlan,
    get_mission_orchestrator,
)


router = APIRouter(prefix="/api/missions", tags=["entity-resolution"])
router.include_router(registry_router)


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IdentityResolutionRequest(ApiModel):
    plan: NextActionPlan
    bootstrap_results: list[BootstrapCrawlResult] = Field(min_length=1)


@router.post(
    "/{mission_id}/resolve-identity",
    response_model=IdentityResolutionResult,
)
def resolve_identity(
    mission_id: str,
    request: IdentityResolutionRequest,
):
    try:
        return get_entity_resolver().resolve(
            get_mission_orchestrator(),
            mission_id,
            plan=request.plan,
            bootstrap_results=request.bootstrap_results,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="mission_not_found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get(
    "/{mission_id}/identity-history",
    response_model=IdentityResolutionHistory,
)
def identity_history(mission_id: str):
    try:
        return get_entity_resolver().history(mission_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail="identity_history_not_found",
        ) from exc
