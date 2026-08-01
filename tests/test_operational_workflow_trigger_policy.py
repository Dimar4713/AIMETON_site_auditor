from pathlib import Path


OPERATIONAL_WORKFLOWS = {
    "stage-retention.yml",
    "stage-observability.yml",
    "project-governance-audit.yml",
    "openstack-recovery-plan-auto.yml",
    "mcp-security-acceptance.yml",
    "project-actual-dates-apply.yml",
    "project-actual-dates-backfill.yml",
    "project-legacy-debt-transfer.yml",
    "project-historical-exceptions-apply.yml",
    "server-architecture-audit.yml",
    "provision-stage-mcp-token.yml",
}


def test_operational_workflows_do_not_subscribe_to_issue_lifecycle_events() -> None:
    workflow_dir = Path(".github/workflows")
    missing = sorted(name for name in OPERATIONAL_WORKFLOWS if not (workflow_dir / name).exists())
    assert not missing, f"missing governed workflows: {missing}"

    offenders: list[str] = []
    for name in sorted(OPERATIONAL_WORKFLOWS):
        text = (workflow_dir / name).read_text(encoding="utf-8")
        trigger_block = text.split("permissions:", 1)[0]
        if "  issues:" in trigger_block:
            offenders.append(name)

    assert not offenders, (
        "Operational workflows must use workflow_dispatch, schedule, workflow_run, "
        f"or an exact issue_comment command; broad issues triggers found: {offenders}"
    )
