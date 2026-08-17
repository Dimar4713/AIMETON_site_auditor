from __future__ import annotations

from app.search_gateway.models import SearchPolicy, SearchStrategy
from app.search_provider_lifecycle import ProviderAvailability, observe_provider_lifecycle
from app.search_strategy_settings import SearchStrategySettings, SearchStrategySettingsRecord


def _runtime_policy() -> SearchPolicy:
    return SearchPolicy(
        provider_order=("yandex", "tavily", "searxng"),
        allowed_providers=frozenset({"yandex", "tavily", "searxng"}),
        strategy=SearchStrategy.FALLBACK_FIRST_NONEMPTY,
        target_results=10,
        max_providers_per_query=3,
        allow_paid_fallback=True,
        allow_paid_fanout=True,
    )


def _admin_record_without_tavily() -> SearchStrategySettingsRecord:
    settings = SearchStrategySettings().model_copy(deep=True)
    settings.global_settings.active_tariff = "max"
    settings.global_settings.enabled_providers = ["searxng", "yandex"]
    settings.tariffs["max"].provider_order = ["searxng", "yandex"]
    settings.tariffs["max"].max_providers_per_query = 2
    settings.validate_relationships()
    return SearchStrategySettingsRecord(
        settings=settings,
        updated_at="2026-08-17T00:00:00+00:00",
        updated_by=1,
        reason="temporary stage profile",
    )


def test_tavily_registration_is_independent_from_admin_activation(monkeypatch) -> None:
    monkeypatch.setenv("TAVILY_TOKEN", "secret-value-not-for-output")
    monkeypatch.setenv("TAVILY_CONTRACT_ALLOWED", "true")

    statuses = observe_provider_lifecycle(
        runtime_policy=_runtime_policy(),
        settings_record=_admin_record_without_tavily(),
    )
    tavily = next(item for item in statuses if item.provider == "tavily")

    assert tavily.registered is True
    assert tavily.configured is True
    assert tavily.availability is ProviderAvailability.UNKNOWN
    assert tavily.availability_evidence == "not_observed"
    assert tavily.enabled is False
    assert tavily.admin_enabled is False
    assert tavily.admin_position is None
    assert tavily.active is True
    assert tavily.runtime_position == 2
    assert "secret-value-not-for-output" not in str(tavily.model_dump(mode="json"))


def test_configuration_is_not_misreported_as_availability(monkeypatch) -> None:
    monkeypatch.setenv("SEARXNG_BASE_URL", "https://search.internal.example")
    monkeypatch.setenv("YANDEX_SEARCH_API_KEY", "key")
    monkeypatch.setenv("YANDEX_CLOUD_FOLDER_ID", "folder")
    monkeypatch.setenv("TAVILY_API_KEY", "key")

    statuses = observe_provider_lifecycle(
        runtime_policy=_runtime_policy(),
        settings_record=SearchStrategySettingsRecord(),
    )

    assert {item.provider for item in statuses} == {"searxng", "yandex", "tavily"}
    assert all(item.registered for item in statuses)
    assert all(item.configured for item in statuses)
    assert all(item.availability is ProviderAvailability.UNKNOWN for item in statuses)
    assert all(item.availability_evidence == "not_observed" for item in statuses)
