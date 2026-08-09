from __future__ import annotations

import hmac

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.auth import User
from app.auth_api import CSRF_COOKIE, CSRF_HEADER, require_admin
from app.hunter_settings import HunterSettings, HunterSettingsRecord
from app.search_strategy_settings import get_search_strategy_settings_repository


router = APIRouter(prefix="/api/admin/hunter-settings", tags=["admin-hunter-settings"])


class HunterSettingsUpdate(BaseModel):
    settings: HunterSettings
    reason: str = Field(min_length=1, max_length=500)


def _require_csrf(cookie_token: str | None, header_token: str | None) -> None:
    if not cookie_token or not header_token or not hmac.compare_digest(cookie_token, header_token):
        raise HTTPException(status_code=403, detail={"reason": "csrf_failed"})


def _record_from_active_tariff() -> HunterSettingsRecord:
    record = get_search_strategy_settings_repository().get()
    profile = record.settings.active_profile()
    return HunterSettingsRecord(
        settings=HunterSettings(
            max_queries=profile.max_queries,
            results_per_query=profile.results_per_query,
            max_candidates=profile.max_candidates,
            minimum_pre_score=profile.minimum_pre_score,
            deep_audit_score=profile.deep_audit_score,
            output_limit=profile.output_limit,
            concurrency=profile.concurrency,
            provider_strategy="fallback_first_nonempty",
        ),
        updated_at=record.updated_at,
        updated_by=record.updated_by,
        reason=record.reason,
    )


@router.get("", response_model=HunterSettingsRecord)
def read_hunter_settings(_admin: User = Depends(require_admin)) -> HunterSettingsRecord:
    """Compatibility projection of the currently active tariff profile."""
    return _record_from_active_tariff()


@router.put("", response_model=HunterSettingsRecord)
def update_hunter_settings(
    payload: HunterSettingsUpdate,
    admin: User = Depends(require_admin),
    csrf_cookie: str | None = Cookie(default=None, alias=CSRF_COOKIE),
    csrf_header: str | None = Header(default=None, alias=CSRF_HEADER),
) -> HunterSettingsRecord:
    """Update numeric Hunter limits of the active tariff without creating a second source of truth."""
    _require_csrf(csrf_cookie, csrf_header)
    repository = get_search_strategy_settings_repository()
    record = repository.get()
    settings = record.settings.model_copy(deep=True)
    profile_id = settings.global_settings.active_tariff
    profile = settings.tariffs[profile_id].model_copy(
        update={
            "max_queries": payload.settings.max_queries,
            "results_per_query": payload.settings.results_per_query,
            "max_candidates": payload.settings.max_candidates,
            "minimum_pre_score": payload.settings.minimum_pre_score,
            "deep_audit_score": payload.settings.deep_audit_score,
            "output_limit": payload.settings.output_limit,
            "concurrency": payload.settings.concurrency,
        }
    )
    settings.tariffs[profile_id] = profile
    try:
        repository.save(settings, actor_id=admin.id, reason=payload.reason)
        return _record_from_active_tariff()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"reason": str(exc)}) from exc
