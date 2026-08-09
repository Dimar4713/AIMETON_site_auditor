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
    assert "apply_search_policy(search_policy_from_env())" in text
    assert "apply_hunt_request(" in text
    assert "httpx" not in text
    assert "/api/hunt" not in text
    assert "provider calls: `0`" in text


def test_hunter_runtime_command_is_authorized_only_on_p1_501() -> None:
    text = ROUTER.read_text(encoding="utf-8")

    assert "accept-hunter-runtime-stage" in text
    assert "workflow_id: 'accept-hunter-runtime-stage.yml'" in text
    route = text.split("'accept-hunter-runtime-stage': {", 1)[1].split("},", 1)[0]
    assert "issue_number: 501" in route
    assert "inputs: {expected_sha: sha}" in route
