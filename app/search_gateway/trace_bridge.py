from __future__ import annotations

from app.search_gateway.models import AttemptState, SearchDiagnostics
from app.search_gateway.trace_projection import provider_waterfall
from app.trace_ledger import SQLiteTraceLedger, TraceEvent, TraceEventCreate, TraceState


_STATE_MAP = {
    AttemptState.SUCCEEDED.value: TraceState.SUCCEEDED,
    AttemptState.CACHE_HIT.value: TraceState.SUCCEEDED,
    AttemptState.EMPTY.value: TraceState.DEGRADED,
    AttemptState.FAILED.value: TraceState.FAILED,
    AttemptState.SKIPPED.value: TraceState.SKIPPED,
}


def persist_provider_waterfall(
    ledger: SQLiteTraceLedger,
    diagnostics: SearchDiagnostics,
    *,
    mission_id: str,
    attempt_id: str,
    query_index: int,
    vertical: str | None = None,
    deployed_sha: str | None = None,
    runtime_version: str | None = None,
) -> list[TraceEvent]:
    """Persist a bounded provider waterfall without query text or raw payloads."""
    events: list[TraceEvent] = []
    for provider_index, row in enumerate(provider_waterfall(diagnostics), start=1):
        reason_code = row["reason"] or row["state"]
        events.append(
            ledger.append(
                TraceEventCreate(
                    mission_id=mission_id,
                    attempt_id=attempt_id,
                    component="search_gateway",
                    operation="provider_attempt",
                    state=_STATE_MAP[row["state"]],
                    reason_code=reason_code,
                    summary=f"Provider {row['provider']} finished with state {row['state']}",
                    provider=row["provider"],
                    vertical=vertical,
                    duration_ms=row["latency_ms"],
                    counters={"results_received": row["results_received"]},
                    metadata={
                        "selected": row["selected"],
                        "called": row["called"],
                        "query_index": query_index,
                        "cost_amount": row["cost"]["amount"],
                        "cost_currency": row["cost"]["currency"],
                    },
                    event_key=(
                        f"{mission_id}:{attempt_id}:search:{query_index}:"
                        f"{provider_index}:{row['provider']}:{row['state']}"
                    ),
                    deployed_sha=deployed_sha,
                    runtime_version=runtime_version,
                )
            )
        )
    return events
