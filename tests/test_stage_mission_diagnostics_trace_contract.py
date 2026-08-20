from pathlib import Path


WORKFLOW = Path(".github/workflows/stage-mission-diagnostics.yml")


def test_routerai_phase_diagnostics_are_read_only_and_sanitized() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    trigger_block = text.split("permissions:", 1)[0]

    assert "workflow_dispatch:" in trigger_block
    assert "issue_comment:" not in trigger_block
    assert "inputs.expected_sha" in text

    assert "AIMETON_TRACE_DB" in text
    assert "mission_trace_events" in text
    assert "component='llm_synthesis'" in text
    assert "operation='llm_finished'" in text
    assert "state='failed'" in text
    assert "mode=ro" in text
    assert "def safe(value" in text

    for field in (
        "failed_phase",
        "phase_error_type",
        "synthesis_mode",
        "duration_ms",
    ):
        assert field in text

    for admission_field in (
        "deployment_sha_match",
        "marker_sha_match",
        "runtime_instance_match",
        "secrets_exposed",
        "marker_error",
        "checks",
    ):
        assert admission_field in text

    assert "provider/LLM calls performed: `no`" in text
    assert "prompt/response/source payloads collected: `no`" in text
    assert "credentials/tokens collected: `no`" in text

    # Diagnostic remains read-only and cannot initiate analysis/provider work.
    assert "/api/analyze/start" not in text
    assert "ROUTERAI_API_KEY" not in text
    assert "routerai.com" not in text
    assert "print(metadata)" not in text
