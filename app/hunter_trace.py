from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.models import HuntRequest
from app.trace_ledger import TraceEventCreate, TraceState
from app.trace_write_metrics import InstrumentedSQLiteTraceLedger


def _ledger() -> InstrumentedSQLiteTraceLedger:
    configured = os.getenv(
        "AIMETON_TRACE_DB",
        os.getenv("AIMETON_RUNTIME_DB", "data/runtime-core.sqlite3"),
    )
    return InstrumentedSQLiteTraceLedger(Path(configured))


def persist_hunter_query_plan(
    *,
    mission_id: str,
    attempt_id: str,
    original: HuntRequest,
    effective: HuntRequest,
    queries: list[str],
    llm_applied: bool,
    corrected_input_summary: str = "",
) -> None:
    """Persist bounded admin diagnostics for the Hunter planning stage.

    This is fail-open and stores no credentials or raw provider payloads.
    """
    try:
        _ledger().append(
            TraceEventCreate(
                mission_id=mission_id,
                attempt_id=attempt_id,
                component="hunter",
                operation="query_plan",
                state=TraceState.SUCCEEDED,
                reason_code="llm_query_intelligence" if llm_applied else "deterministic_fallback",
                summary="Hunter search plan prepared",
                counters={"query_variants": len(queries)},
                metadata={
                    "query_intelligence": "llm" if llm_applied else "fallback",
                    "original_region": original.region[:160],
                    "original_industries": [str(value)[:160] for value in original.industries[:12]],
                    "original_focus": [str(value)[:160] for value in original.focus[:12]],
                    "normalized_region": effective.region[:160],
                    "normalized_industries": [str(value)[:160] for value in effective.industries[:12]],
                    "normalized_focus": [str(value)[:160] for value in effective.focus[:12]],
                    "corrected_input_summary": corrected_input_summary[:500],
                    "query_variants": [" ".join(value.split())[:500] for value in queries[:100]],
                    "max_queries": original.max_queries,
                    "results_per_query": original.results_per_query,
                    "max_candidates": original.max_candidates,
                    "minimum_pre_score": original.minimum_pre_score,
                    "deep_audit_score": original.deep_audit_score,
                    "output_limit": original.output_limit,
                },
                event_key=f"{mission_id}:{attempt_id}:hunter:query-plan",
                runtime_version=os.getenv("AIMETON_RUNTIME_VERSION") or None,
            )
        )
    except Exception:
        pass


def persist_hunter_selection_summary(
    *,
    mission_id: str,
    attempt_id: str,
    raw_results: int,
    unique_domains: int,
    excluded_hosts: int,
    duplicate_domains: int,
    below_minimum_score: int,
    retained_candidates: int,
    returned_candidates: int,
    deep_candidates: int,
    observations: int,
    max_candidates_truncated: bool,
) -> None:
    try:
        _ledger().append(
            TraceEventCreate(
                mission_id=mission_id,
                attempt_id=attempt_id,
                component="hunter",
                operation="selection_summary",
                state=TraceState.SUCCEEDED,
                reason_code="hunter_selection_completed",
                summary="Hunter candidate selection completed",
                counters={
                    "raw_results": raw_results,
                    "unique_domains": unique_domains,
                    "excluded_hosts": excluded_hosts,
                    "duplicate_domains": duplicate_domains,
                    "below_minimum_score": below_minimum_score,
                    "retained_candidates": retained_candidates,
                    "returned_candidates": returned_candidates,
                    "deep_candidates": deep_candidates,
                    "observations": observations,
                },
                metadata={"max_candidates_truncated": bool(max_candidates_truncated)},
                event_key=f"{mission_id}:{attempt_id}:hunter:selection-summary",
                runtime_version=os.getenv("AIMETON_RUNTIME_VERSION") or None,
            )
        )
    except Exception:
        pass
