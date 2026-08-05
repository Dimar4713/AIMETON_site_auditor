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


def _append_stage(
    ledger: SQLiteTraceLedger,
    *,
    mission_id: str,
    attempt_id: str,
    provider: str,
    provider_index: int,
    query_index: int,
    operation: str,
    state: TraceState,
    reason_code: str,
    summary: str,
    counters: dict[str, int] | None = None,
    metadata: dict[str, object] | None = None,
    vertical: str | None = None,
    duration_ms: int | None = None,
    deployed_sha: str | None = None,
    runtime_version: str | None = None,
) -> TraceEvent:
    return ledger.append(
        TraceEventCreate(
            mission_id=mission_id,
            attempt_id=attempt_id,
            component="search_gateway",
            operation=operation,
            state=state,
            reason_code=reason_code,
            summary=summary,
            provider=provider,
            vertical=vertical,
            duration_ms=duration_ms,
            counters=counters or {},
            metadata={"query_index": query_index, **(metadata or {})},
            event_key=(
                f"{mission_id}:{attempt_id}:search:{query_index}:"
                f"{provider_index}:{provider}:{operation}"
            ),
            deployed_sha=deployed_sha,
            runtime_version=runtime_version,
        )
    )


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
    """Persist canonical, bounded provider stages without query text or raw payloads."""
    events: list[TraceEvent] = []
    for provider_index, row in enumerate(provider_waterfall(diagnostics), start=1):
        provider = row["provider"]
        final_state = _STATE_MAP[row["state"]]
        reason_code = row["reason"] or row["state"]
        common_metadata = {
            "final_selected": row["selected"],
            "cost_amount": row["cost"]["amount"],
            "cost_currency": row["cost"]["currency"],
        }

        if row["called"]:
            events.append(
                _append_stage(
                    ledger,
                    mission_id=mission_id,
                    attempt_id=attempt_id,
                    provider=provider,
                    provider_index=provider_index,
                    query_index=query_index,
                    operation="provider_selected",
                    state=TraceState.STARTED,
                    reason_code="provider_selected",
                    summary=f"Provider {provider} selected by search policy",
                    metadata=common_metadata,
                    vertical=vertical,
                    deployed_sha=deployed_sha,
                    runtime_version=runtime_version,
                )
            )
            events.append(
                _append_stage(
                    ledger,
                    mission_id=mission_id,
                    attempt_id=attempt_id,
                    provider=provider,
                    provider_index=provider_index,
                    query_index=query_index,
                    operation="request_started",
                    state=TraceState.STARTED,
                    reason_code="provider_call_started",
                    summary=f"Provider {provider} call started",
                    metadata=common_metadata,
                    vertical=vertical,
                    deployed_sha=deployed_sha,
                    runtime_version=runtime_version,
                )
            )
            events.append(
                _append_stage(
                    ledger,
                    mission_id=mission_id,
                    attempt_id=attempt_id,
                    provider=provider,
                    provider_index=provider_index,
                    query_index=query_index,
                    operation="response_received",
                    state=final_state,
                    reason_code=reason_code,
                    summary=f"Provider {provider} finished with state {row['state']}",
                    counters={"results_received": row["results_received"]},
                    metadata=common_metadata,
                    vertical=vertical,
                    duration_ms=row["latency_ms"],
                    deployed_sha=deployed_sha,
                    runtime_version=runtime_version,
                )
            )
        else:
            events.append(
                _append_stage(
                    ledger,
                    mission_id=mission_id,
                    attempt_id=attempt_id,
                    provider=provider,
                    provider_index=provider_index,
                    query_index=query_index,
                    operation="provider_skipped",
                    state=final_state,
                    reason_code=reason_code,
                    summary=f"Provider {provider} skipped with reason {reason_code}",
                    metadata=common_metadata,
                    vertical=vertical,
                    deployed_sha=deployed_sha,
                    runtime_version=runtime_version,
                )
            )
    return events
