from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.search_provider_attribution import build_latest_hunter_provider_attribution
from app.trace_ledger import SQLiteTraceLedger, TraceEvent, TraceEventCreate, TraceState
from scripts.search_gap_trace_match_inventory import build_inventory_report


def _event(
    seq: int,
    *,
    component: str,
    operation: str,
    provider: str | None = None,
    counters: dict | None = None,
    metadata: dict | None = None,
    mission: str = "hunt-test",
    attempt: str = "corr-test",
) -> TraceEvent:
    return TraceEvent(
        event_id=f"event-{seq}",
        event_key=f"key-{seq}",
        mission_id=mission,
        attempt_id=attempt,
        sequence=seq,
        component=component,
        operation=operation,
        state=TraceState.SUCCEEDED,
        reason_code="test",
        provider=provider,
        counters=counters or {},
        metadata=metadata or {},
        metadata_digest=f"digest-{seq}",
        created_at=datetime(2026, 8, 14, 13, 0, tzinfo=UTC) + timedelta(seconds=seq),
    )


def test_provider_attribution_fails_closed_without_substantial_hunter_attempt():
    report = build_latest_hunter_provider_attribution([], minimum_query_count=2)
    assert report["qualifying_attempt_found"] is False
    assert report["query_count"] == 0
    assert report["retained_unique_domain_count"] == 0


def test_provider_attribution_summarizes_raw_cost_and_retained_domains():
    events = [
        _event(1, component="hunter", operation="hunt_funnel_complete"),
        _event(2, component="search_gateway", operation="query_planned"),
        _event(3, component="search_gateway", operation="query_planned"),
        _event(
            4,
            component="search_gateway",
            operation="response_received",
            provider="searxng",
            counters={"results_received": 5},
            metadata={"cost_amount": "0", "cost_currency": "USD"},
        ),
        _event(
            5,
            component="search_gateway",
            operation="response_received",
            provider="yandex",
            counters={"results_received": 4},
            metadata={"cost_amount": "0.01", "cost_currency": "RUB"},
        ),
        _event(
            6,
            component="search_gateway",
            operation="result_item",
            provider="searxng",
            metadata={"result_url": "https://alpha.example/a", "corroborated_by": ["searxng"]},
        ),
        _event(
            7,
            component="search_gateway",
            operation="result_item",
            provider="yandex",
            metadata={"result_url": "https://beta.example/b", "corroborated_by": ["yandex"]},
        ),
        _event(
            8,
            component="search_gateway",
            operation="result_item",
            provider="searxng",
            metadata={
                "result_url": "https://www.shared.example/one",
                "corroborated_by": ["searxng", "yandex"],
            },
        ),
        _event(
            9,
            component="search_gateway",
            operation="result_item",
            provider="yandex",
            metadata={
                "result_url": "https://shared.example/two",
                "corroborated_by": ["yandex", "searxng"],
            },
        ),
    ]

    report = build_latest_hunter_provider_attribution(events, minimum_query_count=2)
    assert report["qualifying_attempt_found"] is True
    assert report["query_count"] == 2
    assert report["provider_call_count"] == {"searxng": 1, "yandex": 1}
    assert report["provider_raw_result_count"] == {"searxng": 5, "yandex": 4}
    assert report["provider_cost_by_currency"] == {
        "searxng": {"USD": "0"},
        "yandex": {"RUB": "0.01"},
    }
    assert report["retained_result_item_count"] == 4
    assert report["retained_unique_domain_count"] == 3
    assert report["retained_primary_provider_domain_count"] == {"searxng": 2, "yandex": 1}
    assert report["retained_provider_support_domain_count"] == {
        "searxng": 1,
        "searxng+yandex": 1,
        "yandex": 1,
    }
    assert report["retained_corroborated_domain_count"] == 1
    assert report["routing_changed"] is False


def test_provider_attribution_exports_no_query_urls_or_trace_identity():
    events = [
        _event(1, component="hunter", operation="hunt_funnel_complete"),
        _event(2, component="search_gateway", operation="query_planned", metadata={"query_text": "secret query"}),
        _event(3, component="search_gateway", operation="result_item", provider="yandex", metadata={"result_url": "https://secret.example/path"}),
    ]
    report = build_latest_hunter_provider_attribution(events, minimum_query_count=1)
    text = repr(report)
    assert "secret query" not in text
    assert "secret.example" not in text
    assert "hunt-test" not in text
    assert "corr-test" not in text


def test_readonly_inventory_includes_latest_substantial_provider_attribution(tmp_path: Path):
    db = tmp_path / "runtime.sqlite3"
    ledger = SQLiteTraceLedger(db)
    mission = "hunt-live"
    attempt = "corr-live"
    for index in range(20):
        ledger.append(
            TraceEventCreate(
                mission_id=mission,
                attempt_id=attempt,
                component="search_gateway",
                operation="query_planned",
                state=TraceState.STARTED,
                reason_code="query_planned",
                metadata={"query_text": f"hidden query {index}", "query_index": index},
                event_key=f"query-{index}",
            )
        )
    ledger.append(
        TraceEventCreate(
            mission_id=mission,
            attempt_id=attempt,
            component="search_gateway",
            operation="response_received",
            state=TraceState.SUCCEEDED,
            reason_code="results_received",
            provider="yandex",
            counters={"results_received": 20},
            metadata={"cost_amount": "0.01", "cost_currency": "RUB", "query_index": 0},
            event_key="response-yandex",
        )
    )
    ledger.append(
        TraceEventCreate(
            mission_id=mission,
            attempt_id=attempt,
            component="search_gateway",
            operation="result_item",
            state=TraceState.SUCCEEDED,
            reason_code="normalized_search_result",
            provider="yandex",
            metadata={
                "result_url": "https://hidden.example/path",
                "corroborated_by": ["yandex"],
                "query_index": 0,
            },
            event_key="result-yandex",
        )
    )
    ledger.append(
        TraceEventCreate(
            mission_id=mission,
            attempt_id=attempt,
            component="hunter",
            operation="hunt_funnel_complete",
            state=TraceState.SUCCEEDED,
            reason_code="hunt_funnel_complete",
            event_key="funnel",
        )
    )

    report = build_inventory_report(db)
    attribution = report["provider_attribution"]
    assert attribution["qualifying_attempt_found"] is True
    assert attribution["query_count"] == 20
    assert attribution["provider_call_count"] == {"yandex": 1}
    assert attribution["provider_raw_result_count"] == {"yandex": 20}
    assert attribution["provider_cost_by_currency"] == {"yandex": {"RUB": "0.01"}}
    assert attribution["retained_unique_domain_count"] == 1
    assert "hidden query" not in repr(report)
    assert "hidden.example" not in repr(report)
    assert mission not in repr(report)
    assert attempt not in repr(report)
