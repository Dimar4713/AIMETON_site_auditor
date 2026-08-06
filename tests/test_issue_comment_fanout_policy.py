from pathlib import Path


ALLOWED_DIRECT_INGRESS = {
    "aimeton-command-router.yml",
    "project-status-sync.yml",
}

MIGRATED_DOWNSTREAM = {
    "accept-checkpoint-stage.yml",
    "accept-mobile-ui-stage.yml",
}


def _subscribes_to_issue_comment(path: Path) -> bool:
    trigger_block = path.read_text(encoding="utf-8").split("permissions:", 1)[0]
    return "issue_comment:" in trigger_block


def test_first_migrated_downstream_has_no_direct_comment_trigger() -> None:
    workflow_dir = Path(".github/workflows")
    offenders = sorted(
        name for name in MIGRATED_DOWNSTREAM if _subscribes_to_issue_comment(workflow_dir / name)
    )
    assert not offenders, f"migrated workflows regained direct issue_comment: {offenders}"


def test_router_remains_an_allowed_direct_comment_ingress() -> None:
    workflow_dir = Path(".github/workflows")
    direct = {
        path.name for path in workflow_dir.glob("*.yml") if _subscribes_to_issue_comment(path)
    }
    assert "aimeton-command-router.yml" in direct
    assert MIGRATED_DOWNSTREAM.isdisjoint(direct)
    assert ALLOWED_DIRECT_INGRESS & direct
