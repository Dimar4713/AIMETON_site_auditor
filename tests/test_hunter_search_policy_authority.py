from decimal import Decimal
from pathlib import Path

import pytest

import app.hunter_search_policy_authority as policy_authority
from app.hunter_search_policy_authority import (
    HunterSearchPolicyAuthority,
    hunter_search_policy_authority_from_env,
    resolve_hunter_search_policy,
)
from app.search_gateway.models import SearchPolicy, SearchStrategy
from app.search_strategy_settings import (
    SearchStrategyId,
    SearchStrategySettings,
    SearchStrategySettingsRecord,
)


class FakeSettingsRepository:
    def __init__(self, record: SearchStrategySettingsRecord) -> None:
        self.record = record
        self.get_calls = 0

    def get(self) -> SearchStrategySettingsRecord:
        self.get_calls += 1
        return self.record


def _base_policy() -> SearchPolicy:
    return SearchPolicy(
        provider_order=("yandex", "tavily", "searxng"),
        allowed_providers=frozenset({"yandex", "tavily", "searxng"}),
        strategy=SearchStrategy.FALLBACK_FIRST_NONEMPTY,
        target_results=10,
        max_providers_per_query=3,
        allow_paid_fallback=True,
        allow_paid_fanout=True,
        max_cost_by_currency={"RUB": Decimal("999999"), "USD": Decimal("999999")},
    )


def _admin_record(*, persisted: bool) -> SearchStrategySettingsRecord:
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
        updated_at="2026-08-16T00:00:00+00:00" if persisted else None,
        updated_by=1 if persisted else None,
        reason="test persisted admin policy" if persisted else None,
    )


def test_default_authority_is_env_and_preserves_base_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HUNTER_SEARCH_POLICY_AUTHORITY", raising=False)
    base = _base_policy()
    repository = FakeSettingsRepository(_admin_record(persisted=True))

    resolved = resolve_hunter_search_policy(base_policy=base, settings_repository=repository)

    assert resolved.authority is HunterSearchPolicyAuthority.ENV
    assert resolved.policy == base
    assert resolved.selected_policy_fingerprint == resolved.env_policy_fingerprint
    assert resolved.policy_equivalent is False
    assert resolved.admin_policy_persisted is True
    assert repository.get_calls == 1


def test_default_env_authority_does_not_open_admin_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HUNTER_SEARCH_POLICY_AUTHORITY", raising=False)
    base = _base_policy()

    def forbidden_repository_open():
        raise AssertionError("env authority must not acquire an admin SQLite dependency")

    monkeypatch.setattr(policy_authority, "get_search_strategy_settings_repository", forbidden_repository_open)
    resolved = resolve_hunter_search_policy(base_policy=base)

    assert resolved.authority is HunterSearchPolicyAuthority.ENV
    assert resolved.policy == base
    assert resolved.admin_projection_fingerprint is None
    assert resolved.policy_equivalent is None
    assert resolved.admin_policy_persisted is False


def test_loaded_record_is_used_without_repository_reread(monkeypatch: pytest.MonkeyPatch) -> None:
    base = _base_policy()
    record = _admin_record(persisted=True)

    def forbidden_repository_open():
        raise AssertionError("loaded settings record must be the single observation snapshot")

    monkeypatch.setattr(policy_authority, "get_search_strategy_settings_repository", forbidden_repository_open)
    resolved = resolve_hunter_search_policy(
        authority=HunterSearchPolicyAuthority.ADMIN,
        base_policy=base,
        settings_record=record,
    )

    expected = record.settings.apply_search_policy(base)
    assert resolved.policy == expected
    assert resolved.selected_policy_fingerprint == resolved.admin_projection_fingerprint


def test_record_and_repository_cannot_be_mixed() -> None:
    record = _admin_record(persisted=True)
    repository = FakeSettingsRepository(record)

    with pytest.raises(ValueError, match="provide_settings_record_or_repository_not_both"):
        resolve_hunter_search_policy(
            authority=HunterSearchPolicyAuthority.ADMIN,
            base_policy=_base_policy(),
            settings_record=record,
            settings_repository=repository,
        )


def test_explicit_admin_authority_uses_persisted_projection() -> None:
    base = _base_policy()
    record = _admin_record(persisted=True)
    repository = FakeSettingsRepository(record)

    resolved = resolve_hunter_search_policy(
        authority=HunterSearchPolicyAuthority.ADMIN,
        base_policy=base,
        settings_repository=repository,
    )

    expected = record.settings.apply_search_policy(base)
    assert resolved.authority is HunterSearchPolicyAuthority.ADMIN
    assert resolved.policy == expected
    assert resolved.policy.provider_order == ("searxng", "yandex")
    assert resolved.policy.strategy is SearchStrategy.EXHAUSTIVE_COVERAGE
    assert resolved.policy.target_results == 75
    assert resolved.selected_policy_fingerprint == resolved.admin_projection_fingerprint
    assert resolved.policy_equivalent is False


def test_admin_authority_fails_closed_without_persisted_settings() -> None:
    repository = FakeSettingsRepository(_admin_record(persisted=False))

    with pytest.raises(RuntimeError, match="admin_search_policy_not_persisted"):
        resolve_hunter_search_policy(
            authority=HunterSearchPolicyAuthority.ADMIN,
            base_policy=_base_policy(),
            settings_repository=repository,
        )


def test_invalid_authority_environment_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUNTER_SEARCH_POLICY_AUTHORITY", "surprise-mode")

    with pytest.raises(RuntimeError, match="invalid_hunter_search_policy_authority"):
        hunter_search_policy_authority_from_env()


def test_discovery_uses_canonical_hunter_policy_resolver() -> None:
    text = Path("app/discovery.py").read_text(encoding="utf-8")

    assert "from app.hunter_search_policy_authority import resolve_hunter_search_policy" in text
    assert "policy_resolution = resolve_hunter_search_policy()" in text
    assert '"hunt_search_policy_resolved"' in text
    assert "policy = search_policy_from_env()" not in text
