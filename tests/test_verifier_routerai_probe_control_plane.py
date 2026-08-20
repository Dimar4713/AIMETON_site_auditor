from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "verifier-routerai-capability-probe.yml"
ROUTER = ROOT / "scripts" / "aimeton_command_router.py"
REGISTRY = ROOT / "config" / "verifier_model_profiles.json"


def test_probe_is_owner_dispatched_only_and_stage_scoped() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "pull_request:" not in workflow
    assert "push:" not in workflow
    assert "runs-on: [self-hosted, Linux, X64, stage, auditor]" in workflow
    assert "environment: stage" in workflow
    assert "ROUTERAI_API_KEY: ${{ secrets.ROUTERAI_API_KEY }}" in workflow


def test_probe_requires_paid_admission_budget_and_allowlisted_profile() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "inputs.allow_paid_calls" in workflow
    assert "inputs.owner_spend_authorized" in workflow
    assert "0 < budget <= 100.0" in workflow
    assert "VERIFIER_PROFILE: ${{ inputs.profile }}" in workflow
    assert "config/verifier_model_profiles.json" in workflow
    assert "provider calls admitted: `2`" in workflow
    assert "unconstrained + strict json_schema" in workflow


def test_probe_workflow_is_dispatch_parseable_without_runner_context_in_job_env() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "runner.temp" not in workflow
    assert "VERIFIER_RESULT_PATH: /tmp/aimeton-verifier-routerai-capability-${{ github.run_id }}.json" in workflow


def test_probe_does_not_use_marketplace_actions_or_keep_raw_provider_response() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "uses:" not in workflow
    assert "raw provider responses retained: `no`" in workflow
    assert "client release / hard-gate authority: `none`" in workflow


def test_command_router_exposes_only_governed_probe_profiles_on_verifier_issue() -> None:
    router = ROUTER.read_text(encoding="utf-8")

    baseline = (
        '"probe-verifier-routerai-stage": '
        '(783, "verifier-routerai-capability-probe.yml", '
        '{"expected_sha": "{sha}", "allow_paid_calls": "true", '
        '"owner_spend_authorized": "true", "max_budget_rub": "100", '
        '"evidence_issue": "783", "profile": "routerai-gpt4o-mini"})'
    )
    qwen = (
        '"probe-verifier-qwen35-stage": '
        '(783, "verifier-routerai-capability-probe.yml", '
        '{"expected_sha": "{sha}", "allow_paid_calls": "true", '
        '"owner_spend_authorized": "true", "max_budget_rub": "100", '
        '"evidence_issue": "783", "profile": "routerai-qwen35-9b"})'
    )
    assert baseline in router
    assert qwen in router


def test_registry_keeps_model_choice_out_of_router_and_blocks_calibration_by_default() -> None:
    registry = REGISTRY.read_text(encoding="utf-8")
    assert '"routerai-gpt4o-mini"' in registry
    assert '"routerai-qwen35-9b"' in registry
    assert '"openai/gpt-4o-mini"' in registry
    assert '"qwen/qwen3.5-9b"' in registry
    assert registry.count('"calibration_enabled": false') >= 2
    assert '"min_distinct_score_support": 2' in registry
