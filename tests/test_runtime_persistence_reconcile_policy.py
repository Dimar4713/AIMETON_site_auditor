from pathlib import Path
import subprocess

import yaml


WORKFLOW = Path(".github/workflows/runtime-persistence-reconcile.yml")


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _workflow_document() -> dict:
    document = yaml.safe_load(_workflow_text())
    assert isinstance(document, dict)
    return document


def test_runtime_persistence_reconcile_yaml_is_parseable() -> None:
    document = _workflow_document()
    assert "jobs" in document
    assert "reconcile" in document["jobs"]
    steps = document["jobs"]["reconcile"]["steps"]
    parent_gate = next(
        step
        for step in steps
        if step.get("name") == "Require real successful deploy without marketplace actions"
    )
    assert "require_successful_parent_job.py" in parent_gate["run"]
    assert "--job-name deploy" in parent_gate["run"]


def test_runtime_persistence_reconcile_shell_is_parseable() -> None:
    document = _workflow_document()
    steps = document["jobs"]["reconcile"]["steps"]
    reconcile = next(step for step in steps if step.get("name") == "Reconcile persistent runtime storage")
    script = reconcile["run"]
    result = subprocess.run(
        ["bash", "-n"],
        input=script,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_runtime_persistence_reconcile_has_verify_only_path() -> None:
    text = _workflow_text()
    assert "mode='verify-only / no mutation required'" in text
    assert "mutation_required=no" in text
    assert 'if [[ "$compose_correct" != yes || "$mount_correct" != yes ]]; then' in text
    assert "mode='controlled repair'" in text
    assert "verify-only path completed with zero container recreation" in text


def test_runtime_persistence_reconcile_recreates_only_for_repair() -> None:
    text = _workflow_text()
    recreate = 'up -d --force-recreate "$SERVICE"'
    assert text.count(recreate) == 1
    guarded_block = text.split('if [[ "$mutation_required" == yes ]]; then', 1)[1].split("fi", 1)[0]
    assert recreate in guarded_block


def test_runtime_persistence_reconcile_verifies_compose_and_live_mount() -> None:
    text = _workflow_text()
    assert "expected_volume='./data/runtime-core:/app/data'" in text
    assert "compose_correct=no" in text
    assert "mount_correct=no" in text
    assert '[[ "$mount_type" == bind ]]' in text
    assert '[[ "$mount_destination" == \'/app/data\' ]]' in text
    assert '[[ "$(readlink -f "$mount_source")" == "$expected_source" ]]' in text


def test_runtime_persistence_reconcile_repairs_only_with_backup() -> None:
    text = _workflow_text()
    assert 'cp -a "$RUNTIME_COMPOSE" "$backup"' in text
    assert "backup_state='not required'" in text
    assert 'backup_state="created: $backup"' in text
    assert "sed -i -E" in text
    assert "printf '%s\\n' '    volumes:' '      - ./data/runtime-core:/app/data'" in text


def test_runtime_persistence_reconcile_requires_durable_runtime_db() -> None:
    text = _workflow_text()
    assert '[[ "$db_exists" == yes ]]' in text
    assert '[[ "$integrity" == ok ]]' in text
    assert "for required_table in runtime_meta runtime_records runtime_tasks; do" in text
    assert '[[ ",$tables," == *",$required_table,"* ]]' in text
