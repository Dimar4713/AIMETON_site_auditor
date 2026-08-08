from __future__ import annotations

import hashlib
import os
from pathlib import Path

from app.search_gateway.gateway import SearchGateway, request_fingerprint
from app.search_gateway.models import SearchPolicy, SearchRequest, SearchResponse
from app.search_gateway.trace_bridge import persist_provider_waterfall
from app.trace_context import current_trace_identity
from app.trace_ledger import TraceEventCreate, TraceState
from app.trace_write_metrics import InstrumentedSQLiteTraceLedger


class TracedSearchGateway(SearchGateway):
    """Search gateway with fail-open durable diagnostics.

    Search results remain authoritative. Trace persistence is diagnostic only and
    must never turn a successful provider response into a product failure.
    """

    def __init__(self, *args, trace_db_path: str | Path | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        configured = trace_db_path or os.getenv(
            "AIMETON_TRACE_DB",
            os.getenv("AIMETON_RUNTIME_DB", "data/runtime-core.sqlite3"),
        )
        self._trace_ledger = InstrumentedSQLiteTraceLedger(configured)

    async def search(
        self,
        request: SearchRequest,
        policy: SearchPolicy | None = None,
    ) -> SearchResponse:
        fingerprint = request_fingerprint(request).removeprefix("sha256:")
        query_index = int(hashlib.sha256(fingerprint.encode("ascii")).hexdigest()[:8], 16)
        bound = current_trace_identity()
        mission_id = bound.mission_id if bound else request.mission_id
        attempt_id = bound.attempt_id if bound else request.correlation_id

        try:
            self._trace_ledger.append(
                TraceEventCreate(
                    mission_id=mission_id,
                    attempt_id=attempt_id,
                    component="search_gateway",
                    operation="query_planned",
                    state=TraceState.STARTED,
                    reason_code="query_planned",
                    summary="Bounded search query prepared for provider gateway",
                    counters={"requested_limit": request.limit},
                    metadata={
                        "query_index": query_index,
                        "query_text": " ".join(request.query.split())[:500],
                        "language": request.language[:32],
                    },
                    event_key=f"{mission_id}:{attempt_id}:query:{query_index}:planned",
                    runtime_version=os.getenv("AIMETON_RUNTIME_VERSION") or None,
                )
            )
        except Exception:
            pass

        response = await super().search(request, policy)
        try:
            persist_provider_waterfall(
                self._trace_ledger,
                response.diagnostics,
                mission_id=mission_id,
                attempt_id=attempt_id,
                query_index=query_index,
                runtime_version=os.getenv("AIMETON_RUNTIME_VERSION") or None,
            )
        except Exception:
            # Observability is fail-open by design: never suppress search output.
            pass
        return response
