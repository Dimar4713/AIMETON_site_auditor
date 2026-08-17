from __future__ import annotations

from enum import StrEnum
import os

from pydantic import BaseModel

from app.search_gateway.models import SearchPolicy
from app.search_strategy_settings import KNOWN_PROVIDERS, SearchStrategySettingsRecord


class ProviderAvailability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class ProviderLifecycleStatus(BaseModel):
    provider: str
    registered: bool
    configured: bool
    availability: ProviderAvailability = ProviderAvailability.UNKNOWN
    enabled: bool
    active: bool
    runtime_position: int | None = None
    admin_enabled: bool
    admin_position: int | None = None
    availability_evidence: str = "not_observed"


def _nonempty_env(*names: str) -> bool:
    return any((os.getenv(name) or "").strip() for name in names)


def _provider_configured(provider: str) -> bool:
    if provider == "searxng":
        return _nonempty_env("SEARXNG_BASE_URL")
    if provider == "yandex":
        return _nonempty_env("YANDEX_SEARCH_API_KEY") and _nonempty_env(
            "YANDEX_CLOUD_FOLDER_ID", "YANDEX_SEARCH_FOLDER_ID"
        )
    if provider == "tavily":
        token_present = _nonempty_env("TAVILY_TOKEN", "TAVILY_API_KEY")
        contract_allowed = (
            os.getenv("TAVILY_CONTRACT_ALLOWED", "true").strip().lower()
            in {"1", "true", "yes", "on"}
        )
        return token_present and contract_allowed
    return False


def observe_provider_lifecycle(
    *,
    runtime_policy: SearchPolicy,
    settings_record: SearchStrategySettingsRecord,
) -> list[ProviderLifecycleStatus]:
    """Return a zero-cost lifecycle view without probing providers.

    `availability` intentionally remains UNKNOWN until independent health evidence is
    supplied by a future health/telemetry bridge. Configuration or routing policy is
    not treated as proof that an upstream provider is reachable.
    """

    admin_settings = settings_record.settings
    enabled_admin = set(admin_settings.global_settings.enabled_providers)
    admin_profile_order = tuple(admin_settings.active_profile().provider_order)
    runtime_order = tuple(runtime_policy.provider_order)
    runtime_allowed = set(runtime_policy.allowed_providers)

    statuses: list[ProviderLifecycleStatus] = []
    for provider in KNOWN_PROVIDERS:
        runtime_position = runtime_order.index(provider) + 1 if provider in runtime_order else None
        admin_position = admin_profile_order.index(provider) + 1 if provider in admin_profile_order else None
        admin_enabled = provider in enabled_admin and admin_position is not None
        active = provider in runtime_allowed and runtime_position is not None
        statuses.append(
            ProviderLifecycleStatus(
                provider=provider,
                registered=True,
                configured=_provider_configured(provider),
                availability=ProviderAvailability.UNKNOWN,
                enabled=admin_enabled,
                active=active,
                runtime_position=runtime_position,
                admin_enabled=admin_enabled,
                admin_position=admin_position,
            )
        )
    return statuses
