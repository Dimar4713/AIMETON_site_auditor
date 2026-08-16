from pathlib import Path


WORKFLOW = Path(".github/workflows/accept-hunter-runtime-stage.yml")
ROUTER = Path(".github/workflows/aimeton-command-router.yml")


def test_hunter_runtime_acceptance_is_dispatch_only_and_no_cost() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    trigger_block = text.split("permissions:", 1)[0]

    assert "workflow_dispatch:" in trigger_block
    assert "issue_comment:" not in trigger_block
    assert "inputs.expected_sha" in text
    assert "expected_tariff" in text
    assert "expected_strategy" in text
    assert "expected_provider_order" in text
    assert "get_search_strategy_settings_repository" in text
    assert "_execution_policy_observation" in text
    assert "actual_gateway_policy" in text
    assert "projected_admin_gateway_policy" in text
    assert "policy_equivalent" in text
    assert "runtime_callsite_uses_admin_projection" in text
    assert "routing_changed_by_observation" in text
    assert "apply_hunt_request(" in text
    assert "httpx" not in text
    assert "/api/hunt" not in text
    assert "provider calls: `0`" in text


def test_hunter_runtime_acceptance_does_not_claim_projected_policy_is_execution_authority() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "configured admin projection" in text
    assert "actual SearchGateway env policy fingerprint retained separately" in text
    assert "run_hunt()` currently uses env policy directly" in text
    assert "admin projection is observational/configured, not activated" in text


def test_hunter_runtime_command_is_authorized_only_on_p1_501() -> None:
    text = ROUTER.read_text(encoding="utf-8")

    assert "accept-hunter-runtime-stage" in text
    assert "workflow_id: 'accept-hunter-runtime-stage.yml'" in text
    route = text.split("'accept-hunter-runtime-stage': {", 1)[1].split("'accept-logging-pressure-stage': {", 1)[0]
    assert "issue_number: 501" in route
    assert "inputs: {expected_sha: sha}" in route
