from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.identity_evidence.factory import get_identity_evidence_service
from app.identity_evidence.models import (
    IdentityEvidenceResult,
    IdentitySearchResult,
)
from app.mission_orchestrator import (
    NextActionPlan,
    get_mission_orchestrator,
)
from app.scraper import FetchError


router = APIRouter(prefix="/api/missions", tags=["identity-evidence"])


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IdentitySearchRequest(ApiModel):
    plan: NextActionPlan
    identity_result_id: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=5, ge=1, le=10)


class IdentityEvidenceRequest(ApiModel):
    plan: NextActionPlan
    identity_result_id: str = Field(min_length=1, max_length=200)
    identity_search_result_id: str = Field(min_length=1, max_length=200)


@router.post(
    "/{mission_id}/identity-search",
    response_model=IdentitySearchResult,
)
async def search_identity(
    mission_id: str,
    request: IdentitySearchRequest,
):
    try:
        return await get_identity_evidence_service().search_identity(
            get_mission_orchestrator(),
            mission_id,
            plan=request.plan,
            identity_result_id=request.identity_result_id,
            limit=request.limit,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="mission_not_found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/{mission_id}/identity-evidence",
    response_model=IdentityEvidenceResult,
)
async def promote_identity_evidence(
    mission_id: str,
    request: IdentityEvidenceRequest,
):
    try:
        return await get_identity_evidence_service().promote_identity_evidence(
            get_mission_orchestrator(),
            mission_id,
            plan=request.plan,
            identity_result_id=request.identity_result_id,
            identity_search_result_id=request.identity_search_result_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="mission_not_found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FetchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
