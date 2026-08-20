from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "verifier-golden5-live-calibration.yml"
SCRIPT = ROOT / "scripts" / "verifier_golden5_live_calibration.py"
ROUTER = ROOT / "scripts" / "aimeton_command_router.py"


def test_golden5_workflow_is_owner_dispatched_stage_only() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "pull_request:" not in workflow
    assert "push:" not in workflow
    assert "runs-on: [self-hosted, Linux, X64, stage, auditor]" in workflow
    assert "environment: stage" in workflow
    assert "ROUTERAI_API_KEY: ${{ secrets.ROUTERAI_API_KEY }}" in workflow
    assert "uses:" not in workflow
    assert "runner.temp" not in workflow


def test_golden5_workflow_pins_engine_model_and_budget() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "9cabf17e3644778893666b864aec924e740006ba" in workflow
    assert "openai/gpt-4o-mini" in workflow
    assert "inputs.allow_paid_calls" in workflow
    assert "inputs.owner_spend_authorized" in workflow
    assert "5.0 < budget <= 100.0" in workflow
    assert "raw provider responses retained: `no`" in workflow
    assert "client release / hard-gate authority: `none`" in workflow


def test_golden5_harness_is_fail_closed_and_budget_bounded() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert 'MAX_PRIMARY_OUTPUT_TOKENS = 512' in script
    assert 'BUDGET_SAFETY_RESERVE_RUB = 5.0' in script
    assert 'N_EVALUATIONS = 1' in script
    assert 'PIVOTS = 2' in script
    assert 'max_workers=1' in script
    assert 'on_error="raise"' in script
    assert 'expected_score_distribution_events' in script
    assert 'signal_status="valid" if signal_valid else "degraded"' in script
    assert 'raw_provider_response_saved": False' in script
    assert 'candidate_payloads_persisted": False' in script
    assert 'client_release_authority": False' in script
    assert 'hard_gate_override": False' in script


def test_command_router_exposes_golden5_only_on_verifier_issue() -> None:
    router = ROUTER.read_text(encoding="utf-8")

    expected = (
        '"calibrate-verifier-golden5-stage": '
        '(783, "verifier-golden5-live-calibration.yml", '
        '{"expected_sha": "{sha}", "allow_paid_calls": "true", '
        '"owner_spend_authorized": "true", "max_budget_rub": "100", '
        '"evidence_issue": "783", "model": "openai/gpt-4o-mini"})'
    )
    assert expected in router
