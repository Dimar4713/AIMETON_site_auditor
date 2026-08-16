from __future__ import annotations

from app.admin_search_strategy_api import _execution_policy_observation
from app.search_gateway.models import SearchPolicy, SearchStrategy
from app.search_quality_policy_settings import SearchQualityPolicyRecord
from app.search_strategy_settings import SearchStrategySettingsRecord


class _QualityRepo:
    def get(self) -> SearchQualityPolicyRecord:
        return SearchQualityPolicyRecord()


def test_admin_observation_distinguishes_runtime_policy_from_projection(monkeypatch) -> None:
    actual = SearchPolicy(
        provider_order=("yandex", "searxng", "tavily"),
        allowed_providers=frozenset({"yandex", "searxng", "tavily"}),
        strategy=SearchStrategy.FALLBACK_FIRST_NONEMPTY,
        target_results=10,
        max_providers_per_query=3,
        allow_paid_fallback=False,
        allow_paid_fanout=False,
    )
    monkeypatch.setattr("app.admin_search_strategy_api.search_policy_from_env", lambda: actual)
    monkeypatch.setattr(
        "app.admin_search_strategy_api.get_search_quality_policy_repository",
        lambda: _QualityRepo(),
    )

    observation = _execution_policy_observation(SearchStrategySettingsRecord())

    assert observation["runtime_callsite_uses_admin_projection"] is False
    assert observation["routing_changed_by_observation"] is False
    assert observation["actual_gateway_policy"]["fingerprint"].startswith("sha256:")
    assert observation["projected_admin_gateway_policy"]["fingerprint"].startswith("sha256:")
    # Default admin Start profile begins with searxng, while this actual env policy begins with yandex.
    assert observation["policy_equivalent"] is False
    assert observation["actual_gateway_policy"]["provider_order"][0] == "yandex"
    assert observation["projected_admin_gateway_policy"]["provider_order"][0] == "searxng"
