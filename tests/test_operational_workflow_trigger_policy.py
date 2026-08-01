from pathlib import Path


ENFORCED_OPERATIONAL_WORKFLOWS = {
    "stage-retention.yml",
    "stage-observability.yml",
    "server-architecture-audit.yml",
    "provision-stage-mcp-token.yml",
}

TRACKED_TRIGGER_MIGRATION_DEBT = {
    "project-governance-audit.yml",
    "openstack-recovery-plan-auto.yml",
    "mcp-security-acceptance.yml",
    "project-actual-dates-apply.yml",
    "project-actual-dates-backfill.yml",
    "project-legacy-debt-transfer.yml",
    "project-historical-exceptions-apply.yml",
}


def _has_broad_issue_trigger(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    trigger_block = text.split("permissions:", 1)[0]
    return "  issues:" in trigger_block


def test_normalized_operational_workflows_do_not_subscribe_to_issue_lifecycle_events() -> None:
    workflow_dir = Path(".github/workflows")
    missing = sorted(
        name for name in ENFORCED_OPERATIONAL_WORKFLOWS if not (workflow_dir / name).exists()
    )
    assert not missing, f"missing governed workflows: {missing}"

    offenders = sorted(
        name
        for name in ENFORCED_OPERATIONAL_WORKFLOWS
        if _has_broad_issue_trigger(workflow_dir / name)
    )
    assert not offenders, (
        "Normalized operational workflows must use workflow_dispatch, schedule, "
        f"workflow_run, or an exact issue_comment command; offenders: {offenders}"
    )


def test_remaining_trigger_migration_debt_is_explicit_and_exact() -> None:
    workflow_dir = Path(".github/workflows")
    missing = sorted(
        name for name in TRACKED_TRIGGER_MIGRATION_DEBT if not (workflow_dir / name).exists()
    )
    assert not missing, f"missing tracked debt workflows: {missing}"

    actual_debt = sorted(
        name
        for name in TRACKED_TRIGGER_MIGRATION_DEBT
        if _has_broad_issue_trigger(workflow_dir / name)
    )
    assert actual_debt == sorted(TRACKED_TRIGGER_MIGRATION_DEBT), (
        "Trigger migration debt changed. Update the explicit debt set only together "
        f"with read-back evidence. actual={actual_debt}"
    )
