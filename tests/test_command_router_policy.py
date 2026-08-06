from pathlib import Path


ROUTER = Path(".github/workflows/aimeton-command-router.yml")


def test_command_router_is_the_sanitized_single_ingress_contract() -> None:
    text = ROUTER.read_text(encoding="utf-8")

    assert "issue_comment:" in text
    assert "actions: write" in text
    assert "github.event.comment.user.login == 'Dimar4713'" in text
    assert "group: aimeton-command-router-${{ github.event.issue.number }}" in text
    assert "cancel-in-progress: true" in text

    assert "unsupported_or_invalid_command" in text
    assert "Ignored unsupported slash command" in text
    assert "core.setFailed('Unsupported command" not in text

    assert "issue_number: 337" in text
    assert text.count("issue_number: 293") == 2
    assert "issue_number: 88" in text
    assert "issueNumber !== route.issue_number" in text

    for command, workflow in {
        "deploy-stage": "deploy-stage.yml",
        "accept-admin-trace-stage": "accept-admin-trace-stage.yml",
        "accept-aimeton-self-audit-stage": "accept-aimeton-self-audit-stage.yml",
        "accept-checkpoint-stage": "accept-checkpoint-stage.yml",
    }.items():
        assert command in text
        assert workflow in text

    for ledger_field in (
        "command:",
        "target_workflow:",
        "issue:",
        "actor:",
        "exact_sha:",
        "result: dispatched",
    ):
        assert ledger_field in text


def test_router_requires_exact_sha_and_dispatches_main_only() -> None:
    text = ROUTER.read_text(encoding="utf-8")
    assert "([0-9a-f]{40})" in text
    assert "repos.getCommit" in text
    assert "createWorkflowDispatch" in text
    assert "ref: 'main'" in text


def test_checkpoint_acceptance_no_longer_subscribes_to_comments() -> None:
    text = Path(".github/workflows/accept-checkpoint-stage.yml").read_text(encoding="utf-8")
    trigger_block = text.split("permissions:", 1)[0]
    assert "workflow_dispatch:" in trigger_block
    assert "issue_comment:" not in trigger_block
    assert "github.event_name == 'issue_comment'" not in text
    assert "inputs.expected_sha" in text
