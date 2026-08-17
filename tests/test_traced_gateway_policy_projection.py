from __future__ import annotations

from app.search_gateway.models import SearchPolicy, SearchRequest, SearchStrategy
from app.search_gateway.traced_policy import resolve_traced_gateway_policy
from app.search_strategy_settings import SearchStrategySettings, SearchStrategySettingsRecord


def _incoming_env_policy() -> SearchPolicy:
    return SearchPolicy(
        provider_order=("yandex", "tavily", "searxng"),
        allowed_providers=frozenset({"yandex", "tavily", "searxng"}),
        strategy=SearchStrategy.FALLBACK_FIRST_NONEMPTY,
        target_results=10,
        max_providers_per_query=3,
        allow_paid_fallback=True,
        allow_paid_fanout=True,
    )


def _persisted_admin_record() -> SearchStrategySettingsRecord:
    settings = SearchStrategySettings().model_copy(deep=True)
    settings.global_settings.active_tariff = "max"
    settings.global_settings.enabled_providers = ["searxng", "yandex"]
    settings.global_settings.default_strategy = "exhaustive_coverage"
    settings.tariffs["max"].strategy = "exhaustive_coverage"
    settings.tariffs["max"].provider_order = ["searxng", "yandex", "tavily"]
    settings.tariffs["max"].target_results = 75
    settings.tariffs["max"].max_providers_per_query = 3
    settings.validate_relationships()
    return SearchStrategySettingsRecord(
        settings=settings,
        updated_at="2026-08-17T00:00:00+00:00",
        updated_by=1,
        reason="test persisted admin projection",
    )


def test_hunter_request_preserves_current_legacy_admin_reprojection() -> None:
    incoming = _incoming_env_policy()
    request = SearchRequest(
        query="dentistry krasnoyarsk",
        limit=10,
        mission_id="hunt-test-mission",
        correlation_id="corr-test",
    )

    resolution = resolve_traced_gateway_policy(
        request=request,
        incoming_policy=incoming,
        settings_record=_persisted_admin_record(),
    )

    assert resolution.legacy_hunter_admin_projection_applied is True
    assert resolution.policy_changed is True
    assert resolution.incoming_policy_fingerprint != resolution.effective_policy_fingerprint
    assert resolution.effective_policy.provider_order == ("searxng", "yandex")
    assert resolution.effective_policy.allowed_providers == frozenset({"searxng", "yandex"})
    assert resolution.effective_policy.strategy is SearchStrategy.EXHAUSTIVE_COVERAGE
    assert resolution.effective_policy.target_results == 75


def test_non_hunter_request_is_not_reprojected() -> None:
    incoming = _incoming_env_policy()
    request = SearchRequest(
        query="example",
        limit=10,
        mission_id="site-audit-test",
        correlation_id="corr-test",
    )

    resolution = resolve_traced_gateway_policy(
        request=request,
        incoming_policy=incoming,
        settings_record=_persisted_admin_record(),
    )

    assert resolution.legacy_hunter_admin_projection_applied is False
    assert resolution.policy_changed is False
    assert resolution.effective_policy == incoming
    assert resolution.effective_policy_fingerprint == resolution.incoming_policy_fingerprint


def test_hunter_without_settings_record_fails_open_to_incoming_policy() -> None:
    incoming = _incoming_env_policy()
    request = SearchRequest(
        query="example",
        limit=10,
        mission_id="hunt-test-mission",
        correlation_id="corr-test",
    )

    resolution = resolve_traced_gateway_policy(
        request=request,
        incoming_policy=incoming,
        settings_record=None,
    )

    assert resolution.legacy_hunter_admin_projection_applied is False
    assert resolution.policy_changed is False
    assert resolution.effective_policy == incoming
