from __future__ import annotations

from inspect import signature

from app.search_gateway.models import SearchPolicy, SearchRequest, SearchStrategy
from app.search_gateway.traced_policy import resolve_traced_gateway_policy


def _policy() -> SearchPolicy:
    return SearchPolicy(
        provider_order=("searxng", "yandex"),
        allowed_providers=frozenset({"searxng", "yandex"}),
        strategy=SearchStrategy.EXHAUSTIVE_COVERAGE,
        target_results=75,
        max_providers_per_query=2,
        allow_paid_fallback=True,
        allow_paid_fanout=True,
    )


def test_hunter_request_is_provenance_only_and_not_reprojected() -> None:
    incoming = _policy()
    request = SearchRequest(
        query="dentistry krasnoyarsk",
        limit=10,
        mission_id="hunt-test-mission",
        correlation_id="corr-test",
    )

    resolution = resolve_traced_gateway_policy(
        request=request,
        incoming_policy=incoming,
    )

    assert resolution.legacy_hunter_admin_projection_applied is False
    assert resolution.policy_changed is False
    assert resolution.effective_policy == incoming
    assert resolution.effective_policy_fingerprint == resolution.incoming_policy_fingerprint


def test_non_hunter_request_is_also_provenance_only() -> None:
    incoming = _policy()
    request = SearchRequest(
        query="example",
        limit=10,
        mission_id="site-audit-test",
        correlation_id="corr-test",
    )

    resolution = resolve_traced_gateway_policy(
        request=request,
        incoming_policy=incoming,
    )

    assert resolution.legacy_hunter_admin_projection_applied is False
    assert resolution.policy_changed is False
    assert resolution.effective_policy == incoming
    assert resolution.effective_policy_fingerprint == resolution.incoming_policy_fingerprint


def test_traced_policy_boundary_has_no_settings_record_authority_hook() -> None:
    parameters = signature(resolve_traced_gateway_policy).parameters

    assert "settings_record" not in parameters
    assert set(parameters) == {"request", "incoming_policy"}
