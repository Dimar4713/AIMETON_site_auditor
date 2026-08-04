from decimal import Decimal

from app.search_gateway.models import (
    AttemptState,
    FallbackReason,
    GatewayState,
    ProviderAttempt,
    SearchDiagnostics,
)
from app.search_gateway.trace_projection import provider_waterfall


def attempt(provider: str, state: AttemptState, count: int, reason=None):
    return ProviderAttempt(
        provider=provider,
        state=state,
        request_fingerprint="sha256:" + "a" * 64,
        latency_ms=25,
        result_count=count,
        reason=reason,
        cost_amount=Decimal("0"),
        cost_currency="USD",
    )


def test_provider_waterfall_explains_selected_called_and_empty_states():
    diagnostics = SearchDiagnostics(
        state=GatewayState.DEGRADED,
        selected_provider="yandex",
        fallback_used=True,
        attempts=[
            attempt("yandex", AttemptState.EMPTY, 0, FallbackReason.EMPTY_RESULTS),
            attempt("searxng", AttemptState.SUCCEEDED, 3),
            attempt("tavily", AttemptState.SKIPPED, 0, FallbackReason.POLICY_BLOCKED),
        ],
    )

    rows = provider_waterfall(diagnostics)

    assert rows[0] == {
        "provider": "yandex",
        "selected": True,
        "called": True,
        "state": "empty",
        "reason": "empty_results",
        "latency_ms": 25,
        "results_received": 0,
        "cost": {"amount": "0", "currency": "USD"},
    }
    assert rows[1]["results_received"] == 3
    assert rows[2]["called"] is False
    assert "query" not in str(rows).lower()
    assert "token" not in str(rows).lower()
