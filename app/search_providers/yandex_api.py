from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.search_providers.yandex_web import (
    YandexSearchHealth,
    YandexSearchResult,
    get_yandex_web_search_provider,
)

router = APIRouter(tags=["search-provider"])


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class YandexSearchRequest(ApiModel):
    query: str = Field(min_length=1, max_length=500)
    page: int = Field(default=0, ge=0, le=99)
    site: str | None = Field(default=None, max_length=253)


@router.get("/search/yandex/health", response_model=YandexSearchHealth)
def yandex_search_health():
    return get_yandex_web_search_provider().health()


@router.post("/search/yandex/web", response_model=YandexSearchResult)
def yandex_web_search(request: YandexSearchRequest):
    try:
        return get_yandex_web_search_provider().search(
            request.query,
            page=request.page,
            site=request.site,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
