from app.search_strategy_settings import (
    KNOWN_PROVIDERS,
    GlobalSearchSettings,
    default_tariff_profiles,
)


def test_tavily_remains_registered_provider() -> None:
    assert "tavily" in KNOWN_PROVIDERS


def test_tavily_remains_in_canonical_provider_order() -> None:
    settings = GlobalSearchSettings()
    assert "tavily" in settings.canonical_provider_order
    assert "tavily" in settings.enabled_providers


def test_tavily_remains_available_in_paid_default_tariff_templates() -> None:
    profiles = default_tariff_profiles()
    for tariff in ("start", "pro", "max"):
        assert "tavily" in profiles[tariff].provider_order


def test_free_tariff_may_exclude_tavily_without_deregistering_it() -> None:
    profiles = default_tariff_profiles()
    assert profiles["free"].provider_order == ["searxng"]
    assert "tavily" in KNOWN_PROVIDERS
