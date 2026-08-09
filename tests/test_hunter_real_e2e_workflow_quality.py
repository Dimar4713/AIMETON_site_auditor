from pathlib import Path


WORKFLOW = Path(".github/workflows/accept-hunter-real-e2e-stage.yml")


def test_real_e2e_requires_explicit_paid_authorization_and_exact_sha() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "allow_paid_calls" in text
    assert "Require explicit live-cost authorization" in text
    assert "inputs.expected_sha" in text
    assert "Verify exact deployed SHA and healthy auditor" in text


def test_real_e2e_checks_direct_lead_quality_not_only_volume() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "minimum_direct_returned" in text
    assert "_candidate_rank_role" in text
    assert "HuntCandidate.model_validate" in text
    assert "direct_candidate" in text
    assert "supporting_sources_with_deep_analysis" in text
    assert "assert not supporting_deep" in text
    assert "top_direct_window" in text
    assert "assert all(role == 'direct_candidate'" in text


def test_real_e2e_still_checks_public_funnel_and_expected_providers() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "http://127.0.0.1:5000/api/hunt" in text
    assert "hunt_funnel_complete" in text
    assert "raw >= unique >= qualified >= returned" in text
    assert "missing_expected_providers" in text
    assert "provider_attempt_states" in text
    assert "search_total_cost_by_currency" in text
