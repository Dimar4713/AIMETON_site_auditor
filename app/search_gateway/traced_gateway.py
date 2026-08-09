from __future__ import annotations

import hashlib
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from app.search_gateway.gateway import SearchGateway, request_fingerprint
from app.search_gateway.models import SearchItem, SearchPolicy, SearchRequest, SearchResponse
from app.search_gateway.trace_bridge import persist_provider_waterfall
from app.trace_context import current_trace_identity
from app.trace_ledger import TraceEventCreate, TraceState
from app.trace_write_metrics import InstrumentedSQLiteTraceLedger


_TRACE_TITLE_LIMIT = 500
_TRACE_SNIPPET_LIMIT = 1200
_TRACE_URL_LIMIT = 1500


def _diagnostic_url(item: SearchItem) -> str:
    """Return a public result URL without query/fragment tracking material."""
    parts = urlsplit(str(item.url))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))[:_TRACE_URL_LIMIT]


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
        runtime_version = os.getenv("AIMETON_RUNTIME_VERSION") or None

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
                    runtime_version=runtime_version,
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
                runtime_version=runtime_version,
            )
        except Exception:
            # Observability is fail-open by design: never suppress search output.
            pass

        # Persist normalized public result projections as individual bounded trace
        # events. This deliberately stores neither raw provider payloads nor
        # transport/request headers. One event per item avoids the 4 KiB metadata
        # envelope truncating an entire result set.
        for rank, item in enumerate(response.results, start=1):
            try:
                self._trace_ledger.append(
                    TraceEventCreate(
                        mission_id=mission_id,
                        attempt_id=attempt_id,
                        component="search_gateway",
                        operation="result_item",
                        state=TraceState.SUCCEEDED,
                        reason_code="normalized_search_result",
                        summary=f"Normalized search result #{rank} retained for admin diagnostics",
                        provider=item.provider,
                        counters={"result_rank": rank},
                        metadata={
                            "query_index": query_index,
                            "result_rank": rank,
                            "result_url": _diagnostic_url(item),
                            "result_title": item.title[:_TRACE_TITLE_LIMIT],
                            "result_snippet": item.snippet[:_TRACE_SNIPPET_LIMIT],
                            "published_at": item.published_at,
                        },
                        event_key=f"{mission_id}:{attempt_id}:query:{query_index}:result:{rank}",
                        runtime_version=runtime_version,
                    )
                )
            except Exception:
                # Diagnostic persistence is fail-open per item as well.
                pass
        return response
