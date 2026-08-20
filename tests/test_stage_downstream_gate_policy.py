from pathlib import Path


DOWNSTREAM_WORKFLOWS = {
    "configure-dadata-stage.yml": ("deploy", "runtime-persistence-reconcile.yml/dispatches"),
    "runtime-persistence-reconcile.yml": ("deploy", "stage-auth-persistence-guard.yml/dispatches"),
}


def test_stage_mutations_require_real_parent_job_and_direct_handoff() -> None:
    workflow_dir = Path(".github/workflows")
    for name, (parent_job, next_dispatch) in DOWNSTREAM_WORKFLOWS.items():
        text = (workflow_dir / name).read_text(encoding="utf-8")
        assert "actions: write" in text, name
        assert "require_successful_parent_job.py" in text, name
        assert f"--job-name {parent_job}" in text, name
        assert "--allow-manual" in text, name
        assert "Require exact deployed source identity" in text or "Resolve exact deployed source SHA" in text, name
        assert next_dispatch in text, name
        assert "uses: actions/" not in text, name
        assert "ubuntu-latest" not in text, name


def test_closed_runtime_persistence_command_no_longer_subscribes_to_comments() -> None:
    text = (
        Path(".github/workflows/runtime-persistence-reconcile.yml")
        .read_text(encoding="utf-8")
        .split("permissions:", 1)[0]
    )
    assert "issue_comment:" not in text
