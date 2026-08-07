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
    assert text.count("issue_number: 293") == 3
    assert "issue_number: 88" in text
    assert "issue_number: 223" in text
    assert "issue_number: 274" in text
    assert "issue_number: 270" in text
    assert "issue_number: 291" in text
    assert "issue_number: 262" in text
    assert "issue_number: 192" in text
    assert "issue_number: 197" in text
    assert "issue_number: 177" in text
    assert "issue_number: 203" in text
    assert "issue_number: 36" in text
    assert "issueNumber !== route.issue_number" in text

    for command, workflow in {
        "deploy-stage": "deploy-stage.yml",
        "accept-admin-trace-stage": "accept-admin-trace-stage.yml",
        "accept-aimeton-self-audit-stage": "accept-aimeton-self-audit-stage.yml",
        "accept-checkpoint-stage": "accept-checkpoint-stage.yml",
        "accept-mobile-ui-stage": "accept-mobile-ui-stage.yml",
        "accept-service-catalog-stage": "accept-service-catalog-stage.yml",
        "accept-logging-pressure-stage": "accept-logging-pressure-stage.yml",
        "accept-live-analysis-stage": "accept-live-analysis-stage.yml",
        "accept-interface-audit-stage": "interface-audit-stage-acceptance.yml",
        "accept-ui-stage": "ui-stage-visual-audit.yml",
        "accept-user-workspace-stage": "stage-user-workspace-acceptance.yml",
        "accept-admin-workspace-stage": "stage-admin-workspace-acceptance.yml",
        "accept-mission-stage-v2": "stage-mission-ownership-acceptance-v2.yml",
        "accept-integrated-stage-continuity": "stage-integrated-continuity.yml",
        "audit-server-architecture": "server-architecture-audit.yml",
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


def _assert_dispatch_only(path: str) -> None:
    text = Path(path).read_text(encoding="utf-8")
    trigger_block = text.split("permissions:", 1)[0]
    assert "workflow_dispatch:" in trigger_block
    assert "issue_comment:" not in trigger_block
    assert "github.event_name == 'issue_comment'" not in text
    assert "inputs.expected_sha" in text


def test_checkpoint_acceptance_no_longer_subscribes_to_comments() -> None:
    _assert_dispatch_only(".github/workflows/accept-checkpoint-stage.yml")


def test_mobile_acceptance_no_longer_subscribes_to_comments() -> None:
    _assert_dispatch_only(".github/workflows/accept-mobile-ui-stage.yml")


def test_admin_trace_acceptance_no_longer_subscribes_to_comments() -> None:
    _assert_dispatch_only(".github/workflows/accept-admin-trace-stage.yml")


def test_self_audit_acceptance_no_longer_subscribes_to_comments() -> None:
    _assert_dispatch_only(".github/workflows/accept-aimeton-self-audit-stage.yml")


def test_service_catalog_acceptance_no_longer_subscribes_to_comments() -> None:
    _assert_dispatch_only(".github/workflows/accept-service-catalog-stage.yml")


def test_logging_pressure_acceptance_no_longer_subscribes_to_comments() -> None:
    _assert_dispatch_only(".github/workflows/accept-logging-pressure-stage.yml")


def test_live_analysis_acceptance_no_longer_subscribes_to_comments() -> None:
    _assert_dispatch_only(".github/workflows/accept-live-analysis-stage.yml")


def test_interface_audit_acceptance_no_longer_subscribes_to_comments() -> None:
    _assert_dispatch_only(".github/workflows/interface-audit-stage-acceptance.yml")


def test_ui_visual_audit_no_longer_subscribes_to_comments() -> None:
    _assert_dispatch_only(".github/workflows/ui-stage-visual-audit.yml")


def test_user_workspace_acceptance_no_longer_subscribes_to_comments() -> None:
    _assert_dispatch_only(".github/workflows/stage-user-workspace-acceptance.yml")


def test_admin_workspace_acceptance_no_longer_subscribes_to_comments() -> None:
    _assert_dispatch_only(".github/workflows/stage-admin-workspace-acceptance.yml")


def test_mission_ownership_v2_no_longer_subscribes_to_comments() -> None:
    _assert_dispatch_only(".github/workflows/stage-mission-ownership-acceptance-v2.yml")


def test_integrated_continuity_no_longer_subscribes_to_comments() -> None:
    _assert_dispatch_only(".github/workflows/stage-integrated-continuity.yml")


def test_server_architecture_audit_no_longer_subscribes_to_comments() -> None:
    _assert_dispatch_only(".github/workflows/server-architecture-audit.yml")


def test_superseded_mission_ownership_v1_does_not_return() -> None:
    assert not Path(".github/workflows/stage-mission-ownership-acceptance.yml").exists()
