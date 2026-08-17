from pathlib import Path


WORKFLOW = Path(".github/workflows/accept-routerai-synthesis-stage.yml")
ROUTER = Path(".github/workflows/aimeton-command-router.yml")


def test_routerai_synthesis_acceptance_is_dispatch_only_and_cost_gated() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    trigger_block = text.split("permissions:", 1)[0]

    assert "workflow_dispatch:" in trigger_block
    assert "issue_comment:" not in trigger_block
    assert "inputs.expected_sha" in text
    assert "inputs.allow_paid_calls" in text
    assert "inputs.owner_spend_authorized" in text
    assert '[[ "$ALLOW_PAID_CALLS" == \'true\' ]]' in text
    assert '[[ "$OWNER_SPEND_AUTHORIZED" == \'true\' ]]' in text
    assert "Run one Better DeepSeek-origin AIMETON field mission" in text
    assert "llm_terminal_succeeded" in text
    assert "no_llm_timeout" in text
    assert "outer_budget_not_raised" in text
    assert "split_v2_parallel_active" in text


def test_routerai_synthesis_acceptance_uses_canonical_command_router() -> None:
    router = ROUTER.read_text(encoding="utf-8")

    assert "accept-routerai-synthesis-stage" in router
    assert "workflow_id: 'accept-routerai-synthesis-stage.yml'" in router
    assert "issue_number: 700" in router
    assert "allow_paid_calls: 'true'" in router
    assert "owner_spend_authorized: 'true'" in router
