from decimal import Decimal

from app.search_gateway.models import (
    AttemptState,
    FallbackReason,
    GatewayState,
    ProviderAttempt,
    SearchDiagnostics,
)
from app.search_gateway.trace_bridge import persist_provider_waterfall
from app.trace_ledger import SQLiteTraceLedger


def attempt(provider: str, state: AttemptState, count: int, reason=None):
    return ProviderAttempt(
        provider=provider,
        state=state,
        request_fingerprint="sha256:" + "b" * 64,
        latency_ms=31,
        result_count=count,
        reason=reason,
        cost_amount=Decimal("0"),
        cost_currency="USD",
    )


def test_provider_waterfall_is_persisted_idempotently_with_canonical_stages(tmp_path):
    diagnostics = SearchDiagnostics(
        state=GatewayState.DEGRADED,
        selected_provider="searxng",
        fallback_used=True,
        attempts=[
            attempt("yandex", AttemptState.EMPTY, 0, FallbackReason.EMPTY_RESULTS),
            attempt("searxng", AttemptState.SUCCEEDED, 4),
            attempt("tavily", AttemptState.SKIPPED, 0, FallbackReason.POLICY_BLOCKED),
        ],
    )
    ledger = SQLiteTraceLedger(tmp_path / "trace.sqlite3")

    first = persist_provider_waterfall(
        ledger,
        diagnostics,
        mission_id="mission-1",
        attempt_id="attempt-1",
        query_index=2,
        vertical="official",
    )
    duplicate = persist_provider_waterfall(
        ledger,
        diagnostics,
        mission_id="mission-1",
        attempt_id="attempt-1",
        query_index=2,
        vertical="official",
    )

    assert [event.event_id for event in duplicate] == [event.event_id for event in first]
    events = ledger.list_attempt("mission-1", "attempt-1")
    assert [event.sequence for event in events] == list(range(1, 8))
    assert [event.operation for event in events] == [
        "provider_selected", "request_started", "response_received",
        "provider_selected", "request_started", "response_received",
        "provider_skipped",
    ]

    yandex_returned = events[2]
    assert yandex_returned.reason_code == "empty_results"
    assert yandex_returned.state.value == "degraded"
    assert yandex_returned.counters["results_received"] == 0

    searxng_selected = events[3]
    assert searxng_selected.reason_code == "provider_selected"
    assert searxng_selected.metadata == {
        "cost_amount": "0",
        "cost_currency": "USD",
        "final_selected": True,
        "query_index": 2,
    }
    assert events[5].counters["results_received"] == 4

    tavily_skipped = events[6]
    assert tavily_skipped.state.value == "skipped"
    assert tavily_skipped.reason_code == "policy_blocked"
    assert tavily_skipped.metadata["final_selected"] is False
    assert not any(
        event.provider == "tavily" and event.operation == "provider_selected"
        for event in events
    )

    serialized = str([event.model_dump() for event in events]).lower()
    assert "query" not in serialized.replace("query_index", "")
    assert "token" not in serialized
