from __future__ import annotations

import hmac

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.auth import User
from app.auth_api import CSRF_COOKIE, CSRF_HEADER, require_admin
from app.hunter_professional_provenance import (
    fingerprint_model_payload,
    summarize_gateway_policy,
)
from app.search_gateway import search_policy_from_env
from app.search_observer_quality_policy import QualityFirstPromotionPolicy
from app.search_quality_policy_settings import (
    SearchQualityPolicyRecord,
    get_search_quality_policy_repository,
)
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


class SearchQualityPolicyUpdate(BaseModel):
    policy: QualityFirstPromotionPolicy
    reason: str = Field(min_length=1, max_length=500)


def _require_csrf(cookie_token: str | None, header_token: str | None) -> None:
    if not cookie_token or not header_token or not hmac.compare_digest(cookie_token, header_token):
        raise HTTPException(status_code=403, detail={"reason": "csrf_failed"})


def _execution_policy_observation(record: SearchStrategySettingsRecord) -> dict:
    actual = search_policy_from_env()
    projected = record.settings.apply_search_policy(actual)
    actual_summary = summarize_gateway_policy(actual)
    projected_summary = summarize_gateway_policy(projected)
    quality_record = get_search_quality_policy_repository().get()
    return {
        "actual_gateway_policy": actual_summary,
        "projected_admin_gateway_policy": projected_summary,
        "configured_admin_policy_fingerprint": fingerprint_model_payload(record.settings),
        "quality_policy_fingerprint": fingerprint_model_payload(quality_record.policy),
        "policy_equivalent": actual_summary["fingerprint"] == projected_summary["fingerprint"],
        # Current run_hunt() call site passes search_policy_from_env() directly.
        # Keep this explicit so UI/acceptance evidence never mistakes a matching
        # configuration for proof that the admin projection was execution authority.
        "runtime_callsite_uses_admin_projection": False,
        "routing_changed_by_observation": False,
    }


@router.get("")
def read_search_strategy_settings(_admin: User = Depends(require_admin)) -> dict:
    record = get_search_strategy_settings_repository().get()
    return {
        "record": record.model_dump(mode="json"),
        "catalog": [item.model_dump(mode="json") for item in strategy_catalog()],
        "execution_policy_observation": _execution_policy_observation(record),
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


@router.get("/quality-policy", response_model=SearchQualityPolicyRecord)
def read_search_quality_policy(_admin: User = Depends(require_admin)) -> SearchQualityPolicyRecord:
    return get_search_quality_policy_repository().get()


@router.put("/quality-policy", response_model=SearchQualityPolicyRecord)
def update_search_quality_policy(
    payload: SearchQualityPolicyUpdate,
    admin: User = Depends(require_admin),
    csrf_cookie: str | None = Cookie(default=None, alias=CSRF_COOKIE),
    csrf_header: str | None = Header(default=None, alias=CSRF_HEADER),
) -> SearchQualityPolicyRecord:
    _require_csrf(csrf_cookie, csrf_header)
    try:
        return get_search_quality_policy_repository().save(
            payload.policy,
            actor_id=admin.id,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"reason": str(exc)}) from exc
