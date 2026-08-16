from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import os

from app.hunter_professional_provenance import fingerprint_model_payload
from app.search_gateway import SearchPolicy, search_policy_from_env
from app.search_strategy_settings import (
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
    admin_projection_fingerprint: str
    policy_equivalent: bool
    admin_policy_persisted: bool


def hunter_search_policy_authority_from_env() -> HunterSearchPolicyAuthority:
    raw = os.getenv("HUNTER_SEARCH_POLICY_AUTHORITY", HunterSearchPolicyAuthority.ENV.value).strip().lower()
    try:
        return HunterSearchPolicyAuthority(raw)
    except ValueError as exc:
        raise RuntimeError("invalid_hunter_search_policy_authority") from exc


def resolve_hunter_search_policy(
    *,
    authority: HunterSearchPolicyAuthority | None = None,
    base_policy: SearchPolicy | None = None,
    settings_repository: SearchStrategySettingsRepository | None = None,
) -> ResolvedHunterSearchPolicy:
    """Resolve the one SearchGateway policy authority for a Hunter execution.

    The default authority is deliberately the legacy environment policy so merely
    deploying this resolver cannot change provider order, strategy or spend. Admin
    authority is explicit and fail-closed unless a settings record was persisted.
    """

    selected_authority = authority or hunter_search_policy_authority_from_env()
    env_policy = base_policy or search_policy_from_env()
    repository = settings_repository or get_search_strategy_settings_repository()
    record = repository.get()
    admin_projection = record.settings.apply_search_policy(env_policy)

    env_fingerprint = fingerprint_model_payload(env_policy)
    admin_fingerprint = fingerprint_model_payload(admin_projection)
    admin_policy_persisted = record.updated_at is not None

    if selected_authority is HunterSearchPolicyAuthority.ADMIN:
        if not admin_policy_persisted:
            raise RuntimeError("admin_search_policy_not_persisted")
        selected_policy = admin_projection
    else:
        selected_policy = env_policy

    return ResolvedHunterSearchPolicy(
        policy=selected_policy,
        authority=selected_authority,
        selected_policy_fingerprint=fingerprint_model_payload(selected_policy),
        env_policy_fingerprint=env_fingerprint,
        admin_projection_fingerprint=admin_fingerprint,
        policy_equivalent=env_fingerprint == admin_fingerprint,
        admin_policy_persisted=admin_policy_persisted,
    )
