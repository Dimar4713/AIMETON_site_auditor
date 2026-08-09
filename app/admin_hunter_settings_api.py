from __future__ import annotations

import hmac

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.auth import User
from app.auth_api import CSRF_COOKIE, CSRF_HEADER, require_admin
from app.hunter_settings import (
    HunterSettings,
    HunterSettingsRecord,
    get_hunter_settings_repository,
)


router = APIRouter(prefix="/api/admin/hunter-settings", tags=["admin-hunter-settings"])


class HunterSettingsUpdate(BaseModel):
    settings: HunterSettings
    reason: str = Field(min_length=1, max_length=500)


def _require_csrf(cookie_token: str | None, header_token: str | None) -> None:
    if not cookie_token or not header_token or not hmac.compare_digest(cookie_token, header_token):
        raise HTTPException(status_code=403, detail={"reason": "csrf_failed"})


@router.get("", response_model=HunterSettingsRecord)
def read_hunter_settings(_admin: User = Depends(require_admin)) -> HunterSettingsRecord:
    return get_hunter_settings_repository().get()


@router.put("", response_model=HunterSettingsRecord)
def update_hunter_settings(
    payload: HunterSettingsUpdate,
    admin: User = Depends(require_admin),
    csrf_cookie: str | None = Cookie(default=None, alias=CSRF_COOKIE),
    csrf_header: str | None = Header(default=None, alias=CSRF_HEADER),
) -> HunterSettingsRecord:
    _require_csrf(csrf_cookie, csrf_header)
    try:
        return get_hunter_settings_repository().save(
            payload.settings,
            actor_id=admin.id,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"reason": str(exc)}) from exc
