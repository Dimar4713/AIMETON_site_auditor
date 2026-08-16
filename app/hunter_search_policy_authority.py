from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import os

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
    raw = os.getenv("HUNTER_SEARCH_POLICY_AUTHORITY", HunterSearchPolicyAuthority.ENV.value).strip().lower()
    try:
        return HunterSearchPolicyAuthority(raw)
    except ValueError as exc:
        raise RuntimeError("invalid_hunter_search_policy_authority") from exc


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
    """Resolve the one SearchGateway policy authority for a Hunter execution.

    The default authority is deliberately the legacy environment policy so merely
    deploying this resolver cannot change provider order, strategy or spend. In that
    default mode Hunter does not acquire a new SQLite dependency: admin projection
    provenance is loaded only when a settings record/repository is explicitly supplied.
    Admin authority is explicit and fail-closed unless a persisted settings record exists.

    Callers that already loaded an admin record should pass ``settings_record`` so all
    observation/candidate calculations use exactly one immutable settings snapshot.
    """

    selected_authority = authority or hunter_search_policy_authority_from_env()
    env_policy = base_policy or search_policy_from_env()
    env_fingerprint = fingerprint_model_payload(env_policy)

    admin_projection = None
    admin_fingerprint: str | None = None
    admin_policy_persisted = False

    if selected_authority is HunterSearchPolicyAuthority.ADMIN:
        record = _resolve_settings_record(
            settings_record=settings_record,
            settings_repository=settings_repository,
        )
        admin_policy_persisted = record.updated_at is not None
        if not admin_policy_persisted:
            raise RuntimeError("admin_search_policy_not_persisted")
        admin_projection = record.settings.apply_search_policy(env_policy)
        admin_fingerprint = fingerprint_model_payload(admin_projection)
        selected_policy = admin_projection
    else:
        selected_policy = env_policy
        if settings_record is not None or settings_repository is not None:
            record = _resolve_settings_record(
                settings_record=settings_record,
                settings_repository=settings_repository,
            )
            admin_policy_persisted = record.updated_at is not None
            admin_projection = record.settings.apply_search_policy(env_policy)
            admin_fingerprint = fingerprint_model_payload(admin_projection)

    return ResolvedHunterSearchPolicy(
        policy=selected_policy,
        authority=selected_authority,
        selected_policy_fingerprint=fingerprint_model_payload(selected_policy),
        env_policy_fingerprint=env_fingerprint,
        admin_projection_fingerprint=admin_fingerprint,
        policy_equivalent=(env_fingerprint == admin_fingerprint) if admin_fingerprint is not None else None,
        admin_policy_persisted=admin_policy_persisted,
    )
