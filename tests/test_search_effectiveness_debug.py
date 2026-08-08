from decimal import Decimal
from pathlib import Path

from app.search_gateway.factory import search_policy_from_env


ROOT = Path(__file__).resolve().parents[1]


def test_effectiveness_debug_removes_internal_budget_caps(monkeypatch) -> None:
    monkeypatch.setenv("SEARCH_EFFECTIVENESS_DEBUG", "true")
    monkeypatch.setenv("SEARCH_ALLOW_PAID_FALLBACK", "false")
    monkeypatch.setenv("SEARCH_MISSION_BUDGET_USD", "0.008")
    monkeypatch.setenv("SEARCH_MISSION_BUDGET_RUB", "0.01")

    policy = search_policy_from_env()

    assert policy.allow_paid_fallback is True
    assert policy.max_cost_by_currency["USD"] == Decimal("999999")
    assert policy.max_cost_by_currency["RUB"] == Decimal("999999")


def test_normal_mode_keeps_configured_budget_policy(monkeypatch) -> None:
    monkeypatch.delenv("SEARCH_EFFECTIVENESS_DEBUG", raising=False)
    monkeypatch.setenv("SEARCH_ALLOW_PAID_FALLBACK", "false")
    monkeypatch.setenv("SEARCH_MISSION_BUDGET_USD", "0.008")
    monkeypatch.setenv("SEARCH_MISSION_BUDGET_RUB", "0.01")

    policy = search_policy_from_env()

    assert policy.allow_paid_fallback is False
    assert policy.max_cost_by_currency["USD"] == Decimal("0.008")
    assert policy.max_cost_by_currency["RUB"] == Decimal("0.01")


def test_stage_deploy_persists_yandex_and_debug_runtime_contract() -> None:
    deploy = (ROOT / "scripts" / "deploy_stage.sh").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "deploy-stage.yml").read_text(encoding="utf-8")

    assert "YANDEX_SEARCH_API_KEY" in deploy
    assert "YANDEX_CLOUD_FOLDER_ID" in deploy
    assert "YANDEX_SEARCH_COST_RUB" in deploy
    assert "SEARCH_MISSION_BUDGET_RUB" in deploy
    assert "SEARCH_QUOTA_YANDEX" in deploy
    assert "SEARCH_ALLOW_PAID_FALLBACK" in deploy
    assert "SEARCH_EFFECTIVENESS_DEBUG" in deploy

    assert "SEARCH_EFFECTIVENESS_DEBUG: 'true'" in workflow
    assert "SEARCH_ALLOW_PAID_FALLBACK: 'true'" in workflow
