from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.hunter_professional_provenance import fingerprint_model_payload
from app.search_gateway import SearchPolicy, search_policy_from_env
from app.search_strategy_settings import (
    SearchStrategySettingsRecord,
    SearchStrategySettingsRepository,
    get_search_strategy_settings_repository,
)


class HunterSearchPolicyAuthority(StrEnum):
    ENV = "env"
    ADMIN = "admin"


CANONICAL_HUNTER_SEARCH_POLICY_AUTHORITY = HunterSearchPolicyAuthority.ADMIN


@dataclass(frozen=True)
class ResolvedHunterSearchPolicy:
    policy: SearchPolicy
    authority: HunterSearchPolicyAuthority
    selected_policy_fingerprint: str
    env_policy_fingerprint: str
    admin_projection_fingerprint: str | None
    policy_equivalent: bool | None
    admin_policy_persisted: bool


def hunter_search_policy_authority_from_env() -> HunterSearchPolicyAuthority:
    """Compatibility accessor for the now-fixed Hunter policy authority.

    Environment variables still define provider capabilities, credentials and the
    base SearchPolicy, but they no longer select who owns Hunter routing policy.
    Persisted ADMIN SearchStrategySettings are the single canonical authority.
    """

    return CANONICAL_HUNTER_SEARCH_POLICY_AUTHORITY


def _resolve_settings_record(
    *,
    settings_record: SearchStrategySettingsRecord | None,
    settings_repository: SearchStrategySettingsRepository | None,
) -> SearchStrategySettingsRecord:
    if settings_record is not None and settings_repository is not None:
        raise ValueError("provide_settings_record_or_repository_not_both")
    if settings_record is not None:
        return settings_record
    repository = settings_repository or get_search_strategy_settings_repository()
    return repository.get()


def resolve_hunter_search_policy(
    *,
    authority: HunterSearchPolicyAuthority | None = None,
    base_policy: SearchPolicy | None = None,
    settings_record: SearchStrategySettingsRecord | None = None,
    settings_repository: SearchStrategySettingsRepository | None = None,
) -> ResolvedHunterSearchPolicy:
    """Resolve the single canonical SearchGateway policy for Hunter execution.

    Persisted ADMIN SearchStrategySettings own routing policy. Environment-derived
    SearchPolicy remains the capability/credential/budget base onto which the ADMIN
    policy is projected. The resolver fails closed if persisted ADMIN settings are
    unavailable, and explicit attempts to select another authority are rejected.

    Callers that already loaded an admin record should pass ``settings_record`` so
    all observation calculations use one immutable settings snapshot.
    """

    selected_authority = authority or CANONICAL_HUNTER_SEARCH_POLICY_AUTHORITY
    if selected_authority is not CANONICAL_HUNTER_SEARCH_POLICY_AUTHORITY:
        raise RuntimeError("hunter_search_policy_authority_is_canonical_admin")

    env_policy = base_policy or search_policy_from_env()
    env_fingerprint = fingerprint_model_payload(env_policy)

    record = _resolve_settings_record(
        settings_record=settings_record,
        settings_repository=settings_repository,
    )
    admin_policy_persisted = record.updated_at is not None
    if not admin_policy_persisted:
        raise RuntimeError("admin_search_policy_not_persisted")

    admin_projection = record.settings.apply_search_policy(env_policy)
    admin_fingerprint = fingerprint_model_payload(admin_projection)

    return ResolvedHunterSearchPolicy(
        policy=admin_projection,
        authority=selected_authority,
        selected_policy_fingerprint=admin_fingerprint,
        env_policy_fingerprint=env_fingerprint,
        admin_projection_fingerprint=admin_fingerprint,
        policy_equivalent=env_fingerprint == admin_fingerprint,
        admin_policy_persisted=admin_policy_persisted,
    )
