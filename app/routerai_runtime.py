from __future__ import annotations

import asyncio
import os
import time
from functools import lru_cache
from typing import Any

import httpx

from app.llm import analyze_with_routerai
from app.models import SiteAnalysis
from app.trace_context import current_trace_identity
from app.trace_ledger import TraceEventCreate, TraceState
from app.trace_write_metrics import InstrumentedSQLiteTraceLedger


_DEFAULT_ROUTERAI_ANALYSIS_TIMEOUT_SECONDS = 60.0


def _float_env(
    name: str,
    default: float,
    *,
    minimum: float,
    maximum: float,
) -> float:
    try:
        value = float(os.getenv(name, str(default)).strip())
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def routerai_analysis_timeout_seconds() -> float:
    """Bound one analytical LLM turn inside the wider mission deadline."""
    return _float_env(
        "ROUTERAI_ANALYSIS_TIMEOUT_SECONDS",
        _DEFAULT_ROUTERAI_ANALYSIS_TIMEOUT_SECONDS,
        minimum=10.0,
        maximum=120.0,
    )


def _trace_db_path() -> str:
    return os.getenv(
        "AIMETON_TRACE_DB",
        os.getenv("AIMETON_RUNTIME_DB", "data/runtime-core.sqlite3"),
    )


@lru_cache(maxsize=4)
def _trace_ledger_for(path: str) -> InstrumentedSQLiteTraceLedger:
    return InstrumentedSQLiteTraceLedger(path)


def _trace(
    *,
    operation: str,
    state: TraceState,
    reason_code: str,
    summary: str,
    duration_ms: int | None = None,
    budget_seconds: float,
    error_type: str | None = None,
) -> None:
    """Append a safe LLM span event when a mission trace identity is bound."""
    identity = current_trace_identity()
    if identity is None:
        return
    metadata: dict[str, Any] = {
        "budget_seconds": round(budget_seconds, 3),
        "model_family": "routerai",
    }
    if error_type:
        metadata["error_type"] = error_type[:128]
    try:
        _trace_ledger_for(_trace_db_path()).append(
            TraceEventCreate(
                mission_id=identity.mission_id,
                attempt_id=identity.attempt_id,
                component="llm_synthesis",
                operation=operation,
                state=state,
                reason_code=reason_code,
                summary=summary,
                provider="routerai",
                duration_ms=duration_ms,
                metadata=metadata,
                event_key=(
                    f"{identity.mission_id}:{identity.attempt_id}:"
                    f"routerai-analysis:{operation}"
                ),
                runtime_version=os.getenv("AIMETON_RUNTIME_VERSION") or None,
            )
        )
    except Exception:
        # Observability is fail-open and must never break the analytical path.
        return


async def run_bounded_routerai_analysis(
    url: str,
    title: str,
    text: str,
    external_sources: list[dict] | None = None,
) -> SiteAnalysis:
    """Run one RouterAI analysis with a hard wall-clock deadline and trace span."""
    budget_seconds = routerai_analysis_timeout_seconds()
    started = time.perf_counter()
    _trace(
        operation="llm_started",
        state=TraceState.STARTED,
        reason_code="llm_request_inflight",
        summary="RouterAI analytical synthesis started",
        budget_seconds=budget_seconds,
    )
    try:
        result = await asyncio.wait_for(
            analyze_with_routerai(url, title, text, external_sources),
            timeout=budget_seconds,
        )
    except (asyncio.TimeoutError, httpx.TimeoutException) as exc:
        duration_ms = max(0, round((time.perf_counter() - started) * 1000))
        _trace(
            operation="llm_timeout",
            state=TraceState.DEGRADED,
            reason_code="llm_deadline_exceeded",
            summary="RouterAI analytical synthesis exceeded its bounded deadline",
            duration_ms=duration_ms,
            budget_seconds=budget_seconds,
            error_type=type(exc).__name__,
        )
        raise TimeoutError("routerai_analysis_deadline_exceeded") from exc
    except Exception as exc:
        duration_ms = max(0, round((time.perf_counter() - started) * 1000))
        _trace(
            operation="llm_finished",
            state=TraceState.FAILED,
            reason_code="llm_request_failed",
            summary="RouterAI analytical synthesis failed",
            duration_ms=duration_ms,
            budget_seconds=budget_seconds,
            error_type=type(exc).__name__,
        )
        raise

    duration_ms = max(0, round((time.perf_counter() - started) * 1000))
    _trace(
        operation="llm_finished",
        state=TraceState.SUCCEEDED,
        reason_code="llm_request_succeeded",
        summary="RouterAI analytical synthesis completed",
        duration_ms=duration_ms,
        budget_seconds=budget_seconds,
    )
    return result
