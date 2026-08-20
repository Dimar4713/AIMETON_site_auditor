from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

import app.analysis_async_api as async_api
import app.routerai_runtime as routerai_runtime
from app.trace_context import bind_trace_identity


@pytest.mark.asyncio
async def test_routerai_span_is_visible_while_llm_is_running(tmp_path, monkeypatch):
    trace_path = tmp_path / "trace.sqlite3"
    started = asyncio.Event()
    release = asyncio.Event()
    expected = object()

    async def fake_analysis(*args, **kwargs):
        started.set()
        await release.wait()
        return expected

    monkeypatch.setenv("AIMETON_TRACE_DB", str(trace_path))
    monkeypatch.setenv("ROUTERAI_SPLIT_SYNTHESIS", "0")
    monkeypatch.setattr(routerai_runtime, "analyze_with_routerai", fake_analysis)
    monkeypatch.setattr(routerai_runtime, "routerai_analysis_timeout_seconds", lambda: 5.0)
    monkeypatch.setattr(async_api, "_canonical_now", lambda: datetime.now(UTC))
    routerai_runtime._trace_ledger_for.cache_clear()
    async_api._trace_ledger_for.cache_clear()

    with bind_trace_identity("mission-llm-live", "analysis-llm-live"):
        task = asyncio.create_task(
            routerai_runtime.run_bounded_routerai_analysis(
                "https://example.com",
                "Example",
                "Example text",
                [],
            )
        )
        await asyncio.wait_for(started.wait(), timeout=1)

        snapshot = async_api._trace_runtime_snapshot(
            "mission-llm-live",
            "analysis-llm-live",
        )
        assert snapshot["llm_state"] == "running"
        assert snapshot["llm_provider"] == "routerai"
        assert snapshot["llm_budget_seconds"] == 5.0
        assert snapshot["llm_elapsed_seconds"] is not None
        assert snapshot["llm_overdue"] is False

        release.set()
        result = await asyncio.wait_for(task, timeout=1)

    assert result is expected
    finished = async_api._trace_runtime_snapshot(
        "mission-llm-live",
        "analysis-llm-live",
    )
    assert finished["llm_state"] == "succeeded"
    assert finished["llm_provider"] == "routerai"
    assert finished["llm_elapsed_seconds"] is not None

    events = routerai_runtime._trace_ledger_for(str(trace_path)).list_attempt(
        "mission-llm-live",
        "analysis-llm-live",
    )
    terminal = next(event for event in reversed(events) if event.operation == "llm_finished")
    assert terminal.metadata["outcome"] == "succeeded"
    assert terminal.metadata["estimated_total_input_chars"] >= len("Example text")
    assert terminal.metadata["model"]


@pytest.mark.asyncio
async def test_routerai_timeout_is_terminal_in_trace_and_raises_for_local_fallback(
    tmp_path,
    monkeypatch,
):
    trace_path = tmp_path / "trace.sqlite3"

    async def never_finishes(*args, **kwargs):
        await asyncio.sleep(10)

    monkeypatch.setenv("AIMETON_TRACE_DB", str(trace_path))
    monkeypatch.setenv("ROUTERAI_SPLIT_SYNTHESIS", "0")
    monkeypatch.setattr(routerai_runtime, "analyze_with_routerai", never_finishes)
    monkeypatch.setattr(routerai_runtime, "routerai_analysis_timeout_seconds", lambda: 0.02)
    monkeypatch.setattr(async_api, "_canonical_now", lambda: datetime.now(UTC))
    routerai_runtime._trace_ledger_for.cache_clear()
    async_api._trace_ledger_for.cache_clear()

    with bind_trace_identity("mission-llm-timeout", "analysis-llm-timeout"):
        with pytest.raises(TimeoutError, match="routerai_analysis_deadline_exceeded"):
            await routerai_runtime.run_bounded_routerai_analysis(
                "https://example.com",
                "Example",
                "Example text",
                [],
            )

    snapshot = async_api._trace_runtime_snapshot(
        "mission-llm-timeout",
        "analysis-llm-timeout",
    )
    assert snapshot["llm_state"] == "timeout"
    assert snapshot["llm_provider"] == "routerai"
    assert snapshot["llm_elapsed_seconds"] is not None
    assert snapshot["llm_overdue"] is False

    events = routerai_runtime._trace_ledger_for(str(trace_path)).list_attempt(
        "mission-llm-timeout",
        "analysis-llm-timeout",
    )
    terminal = next(event for event in reversed(events) if event.operation == "llm_timeout")
    assert terminal.metadata["outcome"] == "timeout"
    assert terminal.metadata["estimated_total_input_chars"] >= len("Example text")
