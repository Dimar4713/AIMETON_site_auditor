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
    parts = urlsplit(str(item.url))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))[:_TRACE_URL_LIMIT]


class TracedSearchGateway(SearchGateway):
    """Search gateway with fail-open durable diagnostics."""

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
        effective_policy = policy or SearchPolicy()
        if request.mission_id.startswith("hunt-"):
            try:
                from app.search_strategy_settings import get_search_strategy_settings_repository

                effective_policy = get_search_strategy_settings_repository().get().settings.apply_search_policy(effective_policy)
            except Exception:
                # Runtime strategy settings are optional/fail-open. The provided
                # policy remains the safe fallback if the settings record is bad.
                pass

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
                    counters={
                        "requested_limit": request.limit,
                        "target_results": effective_policy.target_results,
                        "max_providers_per_query": effective_policy.max_providers_per_query,
                    },
                    metadata={
                        "query_index": query_index,
                        "query_text": " ".join(request.query.split())[:500],
                        "language": request.language[:32],
                        "search_strategy": str(effective_policy.strategy),
                        "provider_order": list(effective_policy.provider_order),
                        "allowed_providers": sorted(effective_policy.allowed_providers) if effective_policy.allowed_providers is not None else None,
                        "allow_paid_fallback": effective_policy.allow_paid_fallback,
                        "allow_paid_fanout": effective_policy.allow_paid_fanout,
                    },
                    event_key=f"{mission_id}:{attempt_id}:query:{query_index}:planned",
                    runtime_version=runtime_version,
                )
            )
        except Exception:
            pass

        response = await super().search(request, effective_policy)
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
            pass

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
                pass
        return response
