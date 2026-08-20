from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "verifier-routerai-capability-probe.yml"
ROUTER = ROOT / "scripts" / "aimeton_command_router.py"


def test_probe_is_owner_dispatched_only_and_stage_scoped() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "pull_request:" not in workflow
    assert "push:" not in workflow
    assert "runs-on: [self-hosted, Linux, X64, stage, auditor]" in workflow
    assert "environment: stage" in workflow
    assert "ROUTERAI_API_KEY: ${{ secrets.ROUTERAI_API_KEY }}" in workflow


def test_probe_requires_paid_admission_and_budget_cap() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "inputs.allow_paid_calls" in workflow
    assert "inputs.owner_spend_authorized" in workflow
    assert "0 < budget <= 100.0" in workflow
    assert "openai/gpt-4o-mini" in workflow
    assert "provider calls admitted: `1`" in workflow


def test_probe_workflow_is_dispatch_parseable_without_runner_context_in_job_env() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "runner.temp" not in workflow
    assert "VERIFIER_RESULT_PATH: /tmp/aimeton-verifier-routerai-capability-${{ github.run_id }}.json" in workflow


def test_probe_does_not_use_marketplace_actions_or_keep_raw_provider_response() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "uses:" not in workflow
    assert "raw provider response retained: `no`" in workflow
    assert "client release / hard-gate authority: `none`" in workflow


def test_command_router_exposes_probe_only_on_verifier_issue() -> None:
    router = ROUTER.read_text(encoding="utf-8")

    expected = (
        '"probe-verifier-routerai-stage": '
        '(783, "verifier-routerai-capability-probe.yml", '
        '{"expected_sha": "{sha}", "allow_paid_calls": "true", '
        '"owner_spend_authorized": "true", "max_budget_rub": "100", '
        '"evidence_issue": "783", "model": "openai/gpt-4o-mini"})'
    )
    assert expected in router
