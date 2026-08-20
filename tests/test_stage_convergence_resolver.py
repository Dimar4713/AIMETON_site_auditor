from __future__ import annotations

from app.models import SiteAnalysis  # import smoke keeps normal package path active
from scripts.resolve_stage_convergence_gates import resolve_ready_gates, resolve_target_sha


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


def test_automatic_target_requires_successful_main_deploy():
    sha = "b" * 40
    payload = {
        "workflow_run": {
            "name": "Deploy Stage",
            "conclusion": "success",
            "head_branch": "main",
            "head_sha": sha,
        }
    }
    assert resolve_target_sha(event_name="workflow_run", manual_sha="", event_payload=payload) == sha


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


def test_predeploy_or_failed_gate_does_not_converge():
    sha = "d" * 40
    runs = [
        _run("Configure DaData Stage", 1, "2026-08-20T10:00:00Z"),
        _run("Deploy Stage", 2, "2026-08-20T11:00:00Z"),
        _run("Runtime Persistence Reconcile", 4, "2026-08-20T11:02:00Z", conclusion="failure"),
        _run("Stage Auth Persistence Guard", 5, "2026-08-20T11:03:00Z"),
    ]
    assert resolve_ready_gates(runs, sha) is None


def test_import_smoke_is_not_the_acceptance_authority():
    assert SiteAnalysis is not None
