from __future__ import annotations

import hashlib
import os
from pathlib import Path

from app.search_gap_shadow_refinement import ShadowRefinementPlan
from app.search_regime_utility import SearchRegime
from app.trace_ledger import RetentionClass, TraceEventCreate, TraceState
from app.trace_write_metrics import InstrumentedSQLiteTraceLedger


def _query_digest(value: str) -> str:
    normalized = " ".join(value.split()).strip().casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def persist_shadow_follow_up_suggestions(
    *,
    mission_id: str,
    attempt_id: str,
    effective_regime: SearchRegime,
    plan: ShadowRefinementPlan,
    trace_db_path: str | Path | None = None,
) -> int:
    """Persist advisory suggestions plus aggregate persistence outcome.

    This remains observability-only: no suggestion is executed or promoted.
    Failure is fail-open for the product response so trace retention can never
    turn a successful hunt into a failed hunt.
    """
    configured = trace_db_path or os.getenv(
        "AIMETON_TRACE_DB",
        os.getenv("AIMETON_RUNTIME_DB", "data/runtime-core.sqlite3"),
    )
    try:
        ledger = InstrumentedSQLiteTraceLedger(configured)
    except Exception:
        return 0

    persisted = 0
    for index, suggestion in enumerate(plan.suggestions):
        try:
            ledger.append(
                TraceEventCreate(
                    mission_id=mission_id,
                    attempt_id=attempt_id,
                    component="search_refinement_shadow",
                    operation="follow_up_query_suggested",
                    state=TraceState.SUCCEEDED,
                    reason_code=suggestion.reason_code,
                    summary="Gap-driven follow-up query retained as shadow-only advisory evidence",
                    counters={"suggestion_index": index},
                    metadata={
                        "query_text": suggestion.query,
                        "gap_code": suggestion.reason_code,
                        "evidence_target": suggestion.evidence_target,
                        "effective_regime": effective_regime,
                        "routing_changed": False,
                        "steering_enabled": False,
                    },
                    event_key=(
                        f"{mission_id}:{attempt_id}:search-refinement-shadow:"
                        f"{index}:{_query_digest(suggestion.query)}"
                    )[:256],
                    retention_class=RetentionClass.TRACE,
                )
            )
            persisted += 1
        except Exception:
            continue

    try:
        ledger.append(
            TraceEventCreate(
                mission_id=mission_id,
                attempt_id=attempt_id,
                component="search_refinement_shadow",
                operation="refinement_observed",
                state=TraceState.SUCCEEDED,
                reason_code="shadow_refinement_persistence_observed",
                summary="Aggregate gap-driven shadow refinement persistence outcome retained",
                counters={
                    "gap_count": len(plan.gaps),
                    "suggestion_count": len(plan.suggestions),
                    "persisted_suggestion_count": persisted,
                },
                metadata={
                    "effective_regime": effective_regime,
                    "routing_changed": False,
                    "steering_enabled": False,
                    "promotion_activated": False,
                },
                event_key=(
                    f"{mission_id}:{attempt_id}:search-refinement-shadow:refinement-observed"
                )[:256],
                retention_class=RetentionClass.TRACE,
            )
        )
    except Exception:
        pass
    return persisted
