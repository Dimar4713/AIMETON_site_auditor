from __future__ import annotations

import json
from pathlib import Path

import app.runtime_convergence as convergence


def _marker(
    *,
    sha: str,
    instance_id: str,
    checks: dict[str, bool] | None = None,
) -> dict:
    return {
        "schema_version": 1,
        "state": "converged",
        "deployment_sha": sha,
        "runtime_instance_id": instance_id,
        "converged_at_utc": "2026-08-15T13:30:00Z",
        "workflow_runs": {
            "deploy_stage": 1,
            "configure_dadata_stage": 2,
            "runtime_persistence_reconcile": 3,
            "stage_auth_persistence_guard": 4,
        },
        "checks": checks
        or {
            "deploy_stage": True,
            "configure_dadata_stage": True,
            "runtime_persistence_reconcile": True,
            "stage_auth_persistence_guard": True,
        },
        "secret_values_exposed": False,
    }


def _configure(monkeypatch, tmp_path: Path, *, sha: str, instance_id: str) -> Path:
    path = tmp_path / "stage-convergence.json"
    monkeypatch.setenv("AIMETON_DEPLOY_SHA", sha)
    monkeypatch.setenv("AIMETON_STAGE_CONVERGENCE_MARKER", str(path))
    monkeypatch.setattr(convergence, "_RUNTIME_INSTANCE_ID", instance_id)
    return path


def test_missing_marker_is_pending(monkeypatch, tmp_path):
    sha = "a" * 40
    path = _configure(monkeypatch, tmp_path, sha=sha, instance_id="1" * 32)
    assert not path.exists()

    snapshot = convergence.runtime_convergence_snapshot()

    assert snapshot["state"] == "pending"
    assert snapshot["deployment_sha"] == sha
    assert snapshot["marker_present"] is False
    assert snapshot["marker_error"] == "marker_missing"
    assert snapshot["secrets_exposed"] is False


def test_matching_marker_is_converged(monkeypatch, tmp_path):
    sha = "b" * 40
    instance_id = "2" * 32
    path = _configure(monkeypatch, tmp_path, sha=sha, instance_id=instance_id)
    path.write_text(json.dumps(_marker(sha=sha, instance_id=instance_id)), encoding="utf-8")

    snapshot = convergence.runtime_convergence_snapshot()

    assert snapshot["state"] == "converged"
    assert snapshot["marker_error"] is None
    assert snapshot["marker_deployment_sha"] == sha
    assert snapshot["marker_runtime_instance_id"] == instance_id
    assert "deploy_stage" in snapshot["checks"]


def test_restart_makes_persistent_marker_stale(monkeypatch, tmp_path):
    sha = "c" * 40
    old_instance = "3" * 32
    path = _configure(monkeypatch, tmp_path, sha=sha, instance_id="4" * 32)
    path.write_text(json.dumps(_marker(sha=sha, instance_id=old_instance)), encoding="utf-8")

    snapshot = convergence.runtime_convergence_snapshot()

    assert snapshot["state"] == "stale"
    assert snapshot["marker_error"] == "runtime_instance_mismatch"


def test_new_deployment_sha_makes_old_marker_stale(monkeypatch, tmp_path):
    current_sha = "d" * 40
    old_sha = "e" * 40
    instance_id = "5" * 32
    path = _configure(monkeypatch, tmp_path, sha=current_sha, instance_id=instance_id)
    path.write_text(json.dumps(_marker(sha=old_sha, instance_id=instance_id)), encoding="utf-8")

    snapshot = convergence.runtime_convergence_snapshot()

    assert snapshot["state"] == "stale"
    assert snapshot["marker_error"] == "deployment_sha_mismatch"


def test_incomplete_checks_never_report_converged(monkeypatch, tmp_path):
    sha = "f" * 40
    instance_id = "6" * 32
    path = _configure(monkeypatch, tmp_path, sha=sha, instance_id=instance_id)
    path.write_text(
        json.dumps(
            _marker(
                sha=sha,
                instance_id=instance_id,
                checks={"deploy_stage": True, "configure_dadata_stage": False},
            )
        ),
        encoding="utf-8",
    )

    snapshot = convergence.runtime_convergence_snapshot()

    assert snapshot["state"] == "invalid"
    assert snapshot["marker_error"] == "checks_incomplete"
