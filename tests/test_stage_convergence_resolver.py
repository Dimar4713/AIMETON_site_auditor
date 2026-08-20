from __future__ import annotations

import pytest

from scripts.resolve_stage_convergence_gates import (
    readiness_snapshot,
    resolve_ready_gates,
    resolve_target_sha,
)


def _run(name: str, run_id: int, created_at: str, *, conclusion: str = "success") -> dict:
    return {
        "name": name,
        "id": run_id,
        "status": "completed",
        "conclusion": conclusion,
        "created_at": created_at,
    }


def test_manual_target_sha_requires_exact_sha():
    sha = "a" * 40
    assert resolve_target_sha(event_name="workflow_dispatch", manual_sha=sha, event_payload={}) == sha


def test_automatic_target_accepts_each_successful_main_gate_event():
    sha = "b" * 40
    for name in (
        "Deploy Stage",
        "Configure DaData Stage",
        "Runtime Persistence Reconcile",
        "Stage Auth Persistence Guard",
    ):
        payload = {
            "workflow_run": {
                "name": name,
                "conclusion": "success",
                "head_branch": "main",
                "head_sha": sha,
            }
        }
        assert resolve_target_sha(event_name="workflow_run", manual_sha="", event_payload=payload) == sha


def test_automatic_target_rejects_unrelated_or_failed_event():
    sha = "b" * 40
    for payload in (
        {"workflow_run": {"name": "Baseline CI", "conclusion": "success", "head_branch": "main", "head_sha": sha}},
        {"workflow_run": {"name": "Deploy Stage", "conclusion": "failure", "head_branch": "main", "head_sha": sha}},
        {"workflow_run": {"name": "Deploy Stage", "conclusion": "success", "head_branch": "feature", "head_sha": sha}},
    ):
        with pytest.raises(ValueError, match="automatic_convergence_requires_successful_main_gate"):
            resolve_target_sha(event_name="workflow_run", manual_sha="", event_payload=payload)


def test_ready_gates_must_all_be_successful_after_latest_deploy():
    sha = "c" * 40
    runs = [
        _run("Configure DaData Stage", 1, "2026-08-20T10:00:00Z"),
        _run("Deploy Stage", 2, "2026-08-20T11:00:00Z"),
        _run("Configure DaData Stage", 3, "2026-08-20T11:01:00Z"),
        _run("Runtime Persistence Reconcile", 4, "2026-08-20T11:02:00Z"),
        _run("Stage Auth Persistence Guard", 5, "2026-08-20T11:03:00Z"),
    ]
    gates = resolve_ready_gates(runs, sha)
    assert gates is not None
    assert gates.sha == sha
    assert gates.deploy_run_id == 2
    assert gates.dadata_run_id == 3
    assert gates.persistence_run_id == 4
    assert gates.auth_guard_run_id == 5
    assert all(readiness_snapshot(runs).values())


def test_predeploy_or_failed_gate_does_not_converge_and_probe_is_nonblocking():
    sha = "d" * 40
    runs = [
        _run("Configure DaData Stage", 1, "2026-08-20T10:00:00Z"),
        _run("Deploy Stage", 2, "2026-08-20T11:00:00Z"),
        _run("Runtime Persistence Reconcile", 4, "2026-08-20T11:02:00Z", conclusion="failure"),
        _run("Stage Auth Persistence Guard", 5, "2026-08-20T11:03:00Z"),
    ]
    assert resolve_ready_gates(runs, sha) is None
    assert readiness_snapshot(runs) == {
        "Deploy Stage": True,
        "Configure DaData Stage": False,
        "Runtime Persistence Reconcile": False,
        "Stage Auth Persistence Guard": True,
    }
