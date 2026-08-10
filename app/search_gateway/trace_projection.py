from __future__ import annotations

from typing import Any

from app.search_gateway.models import SearchDiagnostics


def provider_waterfall(diagnostics: SearchDiagnostics) -> list[dict[str, Any]]:
    """Build a bounded, secret-free provider execution projection.

    The projection is diagnostic only. It contains provider state, reason,
    latency and result counters, but never query text, request payloads,
    credentials, headers or provider responses.
    """
    rows: list[dict[str, Any]] = []
    for attempt in diagnostics.attempts:
        rows.append(
            {
                "provider": attempt.provider,
                "selected": attempt.provider == diagnostics.selected_provider,
                "called": attempt.state.value not in {"skipped", "cache_hit"},
                "state": attempt.state.value,
                "reason": attempt.reason.value if attempt.reason else None,
                "degraded_upstreams": list(attempt.degraded_upstreams),
                "latency_ms": attempt.latency_ms,
                "results_received": attempt.result_count,
                "cost": {
                    "amount": str(attempt.cost_amount),
                    "currency": attempt.cost_currency,
                },
            }
        )
    return rows
