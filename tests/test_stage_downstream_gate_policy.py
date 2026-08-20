from pathlib import Path


DOWNSTREAM_WORKFLOWS = {
    "runtime-persistence-reconcile.yml": "reconcile",
    "configure-dadata-stage.yml": "configure",
}


def test_stage_mutations_require_successful_parent_deploy_job() -> None:
    workflow_dir = Path(".github/workflows")
    for name, mutation_job in DOWNSTREAM_WORKFLOWS.items():
        text = (workflow_dir / name).read_text(encoding="utf-8")
        assert "actions: write" in text, name
        assert "require_successful_parent_job.py" in text, name
        assert '--job-name deploy' in text, name
        assert '--parent-run-id "${PARENT_RUN_ID:-}"' in text, name
        assert "github.event.workflow_run.conclusion == 'success'" in text, name
        assert "github.event.workflow_run.head_branch == 'main'" in text, name
        assert f"  {mutation_job}:" in text, name
        assert "deployment-gate:" not in text, name
        assert "actions/github-script" not in text, name


def test_closed_runtime_persistence_command_no_longer_subscribes_to_comments() -> None:
    text = (
        Path(".github/workflows/runtime-persistence-reconcile.yml")
        .read_text(encoding="utf-8")
        .split("permissions:", 1)[0]
    )
    assert "issue_comment:" not in text
