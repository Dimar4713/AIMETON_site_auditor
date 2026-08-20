from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import app.analysis_async_api as async_api


class _FakeLedger:
    def __init__(self, events):
        self._events = events

    def list_attempt(self, mission_id: str, attempt_id: str):
        assert mission_id == "mission-public"
        assert attempt_id == "analysis-public"
        return list(self._events)


def _event(
    operation: str,
    *,
    created_at: datetime,
    metadata: dict,
    state: str = "succeeded",
    provider: str | None = "routerai",
    duration_ms: int | None = None,
):
    return SimpleNamespace(
        operation=operation,
        created_at=created_at,
        metadata=metadata,
        state=SimpleNamespace(value=state),
        provider=provider,
        duration_ms=duration_ms,
    )


def test_trace_runtime_snapshot_projects_only_safe_llm_aggregates(monkeypatch) -> None:
    started_at = datetime(2026, 8, 20, 9, 0, tzinfo=UTC)
    finished_at = started_at + timedelta(seconds=60)
    events = [
        _event(
            "llm_started",
            created_at=started_at,
            metadata={
                "budget_seconds": 60,
                "official_text_chars": 30000,
                "external_context_chars": 52000,
                "external_source_count": 17,
                "schema_chars": 12000,
                "estimated_total_input_chars": 94000,
                "prompt": "PRIVATE PROMPT",
                "query": "PRIVATE QUERY",
                "url": "https://private.example/secret",
                "raw_response": "PRIVATE RESPONSE",
                "provider_payload": {"token": "PRIVATE TOKEN"},
                "model": "private/model-id",
            },
        ),
        _event(
            "llm_timeout",
            created_at=finished_at,
            duration_ms=60000,
            state="failed",
            metadata={
                "outcome": "timeout",
                "raw_response": "PRIVATE TERMINAL RESPONSE",
            },
        ),
    ]
    monkeypatch.setattr(async_api, "_trace_ledger_for", lambda path: _FakeLedger(events))
    monkeypatch.setattr(async_api, "_canonical_now", lambda: finished_at)

    snapshot = async_api._trace_runtime_snapshot("mission-public", "analysis-public")

    assert snapshot["llm_state"] == "timeout"
    assert snapshot["llm_outcome"] == "timeout"
    assert snapshot["llm_input_metrics"] == {
        "official_text_chars": 30000,
        "external_context_chars": 52000,
        "external_source_count": 17,
        "schema_chars": 12000,
        "estimated_total_input_chars": 94000,
    }
    assert snapshot["llm_elapsed_seconds"] == 60.0
    rendered = json.dumps(snapshot, ensure_ascii=False)
    for forbidden in (
        "PRIVATE PROMPT",
        "PRIVATE QUERY",
        "private.example",
        "PRIVATE RESPONSE",
        "PRIVATE TOKEN",
        "private/model-id",
        "PRIVATE TERMINAL RESPONSE",
    ):
        assert forbidden not in rendered


def test_trace_runtime_snapshot_is_null_safe_without_llm_trace(monkeypatch) -> None:
    monkeypatch.setattr(async_api, "_trace_ledger_for", lambda path: _FakeLedger([]))
    monkeypatch.setattr(
        async_api,
        "_canonical_now",
        lambda: datetime(2026, 8, 20, 9, 0, tzinfo=UTC),
    )

    snapshot = async_api._trace_runtime_snapshot("mission-public", "analysis-public")

    assert snapshot["llm_input_metrics"] is None
    assert snapshot["llm_outcome"] is None
