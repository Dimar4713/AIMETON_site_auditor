from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

from app.policy_fingerprint import fingerprint_model_payload
from app.search_gateway.models import SearchPolicy, SearchRequest

if TYPE_CHECKING:
    from app.search_strategy_settings import SearchStrategySettingsRecord


class TracedGatewayPolicyResolution(BaseModel):
    incoming_policy: SearchPolicy
    effective_policy: SearchPolicy
    incoming_policy_fingerprint: str
    effective_policy_fingerprint: str
    legacy_hunter_admin_projection_applied: bool
    policy_changed: bool


def resolve_traced_gateway_policy(
    *,
    request: SearchRequest,
    incoming_policy: SearchPolicy,
    settings_record: SearchStrategySettingsRecord | None = None,
) -> TracedGatewayPolicyResolution:
    """Resolve the compatibility policy layer applied by TracedSearchGateway.

    This function is deliberately pure: it never reads persistence and never calls a
    provider. The caller may pass the already-loaded settings record when preserving
    the legacy Hunter re-projection behavior. A later migration can remove that
    compatibility layer without changing how provenance is computed.
    """

    effective_policy = incoming_policy
    projection_applied = False
    if request.mission_id.startswith("hunt-") and settings_record is not None:
        effective_policy = settings_record.settings.apply_search_policy(incoming_policy)
        projection_applied = True

    incoming_fingerprint = fingerprint_model_payload(incoming_policy)
    effective_fingerprint = fingerprint_model_payload(effective_policy)
    return TracedGatewayPolicyResolution(
        incoming_policy=incoming_policy,
        effective_policy=effective_policy,
        incoming_policy_fingerprint=incoming_fingerprint,
        effective_policy_fingerprint=effective_fingerprint,
        legacy_hunter_admin_projection_applied=projection_applied,
        policy_changed=incoming_fingerprint != effective_fingerprint,
    )
