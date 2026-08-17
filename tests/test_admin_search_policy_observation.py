from __future__ import annotations

from app.admin_search_strategy_api import _execution_policy_observation
from app.search_gateway.models import SearchPolicy, SearchStrategy
from app.search_quality_policy_settings import SearchQualityPolicyRecord
from app.search_strategy_settings import (
    SearchStrategyId,
    SearchStrategySettings,
    SearchStrategySettingsRecord,
)


class _QualityRepo:
    def get(self) -> SearchQualityPolicyRecord:
        return SearchQualityPolicyRecord()


def _actual_policy() -> SearchPolicy:
    return SearchPolicy(
        provider_order=("yandex", "searxng", "tavily"),
        allowed_providers=frozenset({"yandex", "searxng", "tavily"}),
        strategy=SearchStrategy.FALLBACK_FIRST_NONEMPTY,
        target_results=10,
        max_providers_per_query=3,
        allow_paid_fallback=False,
        allow_paid_fanout=False,
    )


def _persisted_admin_record() -> SearchStrategySettingsRecord:
    settings = SearchStrategySettings().model_copy(deep=True)
    settings.global_settings.active_tariff = "max"
    settings.tariffs["max"].strategy = SearchStrategyId.EXHAUSTIVE_COVERAGE
    settings.tariffs["max"].provider_order = ["searxng", "yandex"]
    settings.tariffs["max"].target_results = 75
    settings.tariffs["max"].max_providers_per_query = 2
    settings.global_settings.enabled_providers = ["searxng", "yandex"]
    settings.validate_relationships()
    return SearchStrategySettingsRecord(
        settings=settings,
        updated_at="2026-08-16T00:00:00+00:00",
        updated_by=1,
        reason="test persisted admin policy",
    )


def _patch_observation_dependencies(monkeypatch, actual: SearchPolicy) -> None:
    monkeypatch.setattr("app.admin_search_strategy_api.search_policy_from_env", lambda: actual)
    monkeypatch.setattr(
        "app.admin_search_strategy_api.get_search_quality_policy_repository",
        lambda: _QualityRepo(),
    )


def test_admin_observation_exposes_hidden_gateway_reprojection_for_env_authority(monkeypatch) -> None:
    actual = _actual_policy()
    record = _persisted_admin_record()
    _patch_observation_dependencies(monkeypatch, actual)
    monkeypatch.setenv("HUNTER_SEARCH_POLICY_AUTHORITY", "env")

    observation = _execution_policy_observation(record)

    assert observation["runtime_authority"] == "env"
    assert observation["runtime_callsite_uses_admin_projection"] is False
    assert observation["routing_changed_by_observation"] is False
    assert observation["selected_gateway_policy"] == observation["actual_gateway_policy"]
    assert (
        observation["selected_policy_fingerprint"]
        == observation["actual_gateway_policy"]["fingerprint"]
    )
    assert observation["actual_gateway_policy"]["provider_order"][0] == "yandex"
    assert observation["projected_admin_gateway_policy"]["provider_order"][0] == "searxng"
    assert observation["policy_equivalent"] is False

    assert observation["legacy_hunter_admin_projection_applied"] is True
    assert observation["gateway_policy_changed_after_authority_resolution"] is True
    assert (
        observation["gateway_effective_policy"]
        == observation["projected_admin_gateway_policy"]
    )
    assert (
        observation["gateway_effective_policy_fingerprint"]
        == observation["projected_admin_gateway_policy"]["fingerprint"]
    )
    assert observation["gateway_effective_policy_fingerprint"] != observation["selected_policy_fingerprint"]


def test_admin_candidate_matches_persisted_projection_without_activation(monkeypatch) -> None:
    actual = _actual_policy()
    record = _persisted_admin_record()
    _patch_observation_dependencies(monkeypatch, actual)
    monkeypatch.setenv("HUNTER_SEARCH_POLICY_AUTHORITY", "env")

    observation = _execution_policy_observation(record)

    assert observation["runtime_authority"] == "env"
    assert observation["admin_candidate_available"] is True
    assert observation["admin_candidate_matches_projection"] is True
    assert (
        observation["admin_candidate_policy_fingerprint"]
        == observation["projected_admin_gateway_policy"]["fingerprint"]
    )
    assert (
        observation["admin_candidate_gateway_policy"]
        == observation["projected_admin_gateway_policy"]
    )
    assert observation["selected_policy_fingerprint"] != observation["admin_candidate_policy_fingerprint"]
    assert observation["gateway_effective_policy_fingerprint"] == observation["admin_candidate_policy_fingerprint"]


def test_admin_observation_tracks_future_admin_authority_dynamically(monkeypatch) -> None:
    actual = _actual_policy()
    record = _persisted_admin_record()
    _patch_observation_dependencies(monkeypatch, actual)
    monkeypatch.setenv("HUNTER_SEARCH_POLICY_AUTHORITY", "admin")

    observation = _execution_policy_observation(record)

    assert observation["runtime_authority"] == "admin"
    assert observation["runtime_callsite_uses_admin_projection"] is True
    assert observation["selected_gateway_policy"] == observation["projected_admin_gateway_policy"]
    assert (
        observation["selected_policy_fingerprint"]
        == observation["projected_admin_gateway_policy"]["fingerprint"]
    )
    assert observation["legacy_hunter_admin_projection_applied"] is True
    assert observation["gateway_policy_changed_after_authority_resolution"] is False
    assert observation["gateway_effective_policy"] == observation["selected_gateway_policy"]
    assert observation["admin_candidate_matches_projection"] is True
    assert observation["routing_changed_by_observation"] is False


def test_unpersisted_admin_record_has_no_admin_candidate(monkeypatch) -> None:
    actual = _actual_policy()
    _patch_observation_dependencies(monkeypatch, actual)
    monkeypatch.setenv("HUNTER_SEARCH_POLICY_AUTHORITY", "env")

    observation = _execution_policy_observation(SearchStrategySettingsRecord())

    assert observation["runtime_authority"] == "env"
    assert observation["admin_candidate_available"] is False
    assert observation["admin_candidate_gateway_policy"] is None
    assert observation["admin_candidate_policy_fingerprint"] is None
    assert observation["admin_candidate_matches_projection"] is None
    # Legacy TracedSearchGateway behavior still applies the loaded/default settings
    # record independently of whether it was explicitly persisted.
    assert observation["legacy_hunter_admin_projection_applied"] is True
