from __future__ import annotations

import hmac

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.auth import User
from app.auth_api import CSRF_COOKIE, CSRF_HEADER, require_admin
from app.search_strategy_settings import (
    SearchStrategySettings,
    SearchStrategySettingsRecord,
    get_search_strategy_settings_repository,
    strategy_catalog,
)


router = APIRouter(prefix="/api/admin/search-strategies", tags=["admin-search-strategies"])


class SearchStrategySettingsUpdate(BaseModel):
    settings: SearchStrategySettings
    reason: str = Field(min_length=1, max_length=500)


def _require_csrf(cookie_token: str | None, header_token: str | None) -> None:
    if not cookie_token or not header_token or not hmac.compare_digest(cookie_token, header_token):
        raise HTTPException(status_code=403, detail={"reason": "csrf_failed"})


@router.get("")
def read_search_strategy_settings(_admin: User = Depends(require_admin)) -> dict:
    record = get_search_strategy_settings_repository().get()
    return {
        "record": record.model_dump(mode="json"),
        "catalog": [item.model_dump(mode="json") for item in strategy_catalog()],
    }


@router.put("", response_model=SearchStrategySettingsRecord)
def update_search_strategy_settings(
    payload: SearchStrategySettingsUpdate,
    admin: User = Depends(require_admin),
    csrf_cookie: str | None = Cookie(default=None, alias=CSRF_COOKIE),
    csrf_header: str | None = Header(default=None, alias=CSRF_HEADER),
) -> SearchStrategySettingsRecord:
    _require_csrf(csrf_cookie, csrf_header)
    try:
        return get_search_strategy_settings_repository().save(
            payload.settings,
            actor_id=admin.id,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"reason": str(exc)}) from exc
