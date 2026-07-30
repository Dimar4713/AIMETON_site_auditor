from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.entity_resolution.dadata import (
    DaDataLookupResult,
    DaDataProviderHealth,
    get_dadata_registry_mirror_provider,
)


router = APIRouter(tags=["registry-mirror"])


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DaDataLookupRequest(ApiModel):
    query: str = Field(min_length=1, max_length=300)


@router.get(
    "/registry-mirror/dadata/health",
    response_model=DaDataProviderHealth,
)
def dadata_registry_mirror_health():
    return get_dadata_registry_mirror_provider().health()


@router.post(
    "/registry-mirror/dadata/find-party",
    response_model=DaDataLookupResult,
)
def dadata_find_party(request: DaDataLookupRequest):
    try:
        return get_dadata_registry_mirror_provider().lookup(request.query)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
