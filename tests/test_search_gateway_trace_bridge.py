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


def test_provider_waterfall_is_persisted_idempotently_without_query(tmp_path):
    diagnostics = SearchDiagnostics(
        state=GatewayState.DEGRADED,
        selected_provider="yandex",
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
    assert [event.sequence for event in events] == [1, 2, 3]
    assert events[0].reason_code == "empty_results"
    assert events[0].metadata == {
        "called": True,
        "cost_amount": "0",
        "cost_currency": "USD",
        "query_index": 2,
        "selected": True,
    }
    assert events[1].counters["results_received"] == 4
    assert events[2].state.value == "skipped"
    serialized = str([event.model_dump() for event in events]).lower()
    assert "query" not in serialized.replace("query_index", "")
    assert "token" not in serialized
