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
    assert "component = 'llm_synthesis'" in text
    assert "operation = 'llm_finished'" in text
    assert "state = 'failed'" in text
    assert "mode=ro" in text

    for field in (
        "failed_phase",
        "phase_error_type",
        "error_type",
        "synthesis_mode",
        "budget_seconds",
        "duration_ms",
    ):
        assert field in text

    assert "hashlib.sha256" in text
    assert "mission_sha" in text
    assert "attempt_sha" in text
    assert "RouterAI trace identifiers: SHA-256 prefixes only" in text
    assert "RouterAI prompt/response/source payloads: not collected" in text

    # The diagnostic must not initiate a new analysis or touch provider credentials.
    assert "/api/analyze/start" not in text
    assert "ROUTERAI_API_KEY" not in text
    assert "routerai.com" not in text
    assert "print(metadata)" not in text
