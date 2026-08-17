from __future__ import annotations

from pydantic import BaseModel

from app.policy_fingerprint import fingerprint_model_payload
from app.search_gateway.models import SearchPolicy, SearchRequest


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
) -> TracedGatewayPolicyResolution:
    """Observe the policy received by TracedSearchGateway without mutating it.

    Hunter routing authority is resolved upstream by the canonical Hunter policy
    resolver. Tracing is therefore provenance-only: it must never read persistence,
    re-project ADMIN settings or otherwise change the selected SearchPolicy.
    ``request`` remains part of the boundary so provenance can evolve without
    reintroducing routing authority here.
    """

    _ = request
    incoming_fingerprint = fingerprint_model_payload(incoming_policy)
    return TracedGatewayPolicyResolution(
        incoming_policy=incoming_policy,
        effective_policy=incoming_policy,
        incoming_policy_fingerprint=incoming_fingerprint,
        effective_policy_fingerprint=incoming_fingerprint,
        legacy_hunter_admin_projection_applied=False,
        policy_changed=False,
    )
