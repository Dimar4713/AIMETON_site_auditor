from datetime import UTC, datetime
from pathlib import Path

from app.search_gap_trace_match_inventory import build_shadow_query_match_summary
from app.trace_ledger import SQLiteTraceLedger, TraceEvent, TraceEventCreate, TraceState
from scripts.search_gap_trace_match_inventory import build_inventory_report


def _event(
    seq: int,
    *,
    mission: str = "m1",
    attempt: str = "a1",
    component: str,
    operation: str,
    metadata: dict | None = None,
) -> TraceEvent:
    return TraceEvent(
        event_id=f"event-{seq}-{component}-{operation}",
        event_key=f"key-{seq}-{component}-{operation}",
        mission_id=mission,
        attempt_id=attempt,
        sequence=seq,
        component=component,
        operation=operation,
        state=TraceState.SUCCEEDED,
        reason_code="test",
        metadata=metadata or {},
        metadata_digest=f"digest-{seq}-{component}-{operation}",
        created_at=datetime.now(UTC),
    )


def test_readiness_reports_no_hunter_traffic_without_overclaiming():
    report = build_shadow_query_match_summary([])
    assert report["corpus_state"] == "no_hunter_traffic"
    assert report["hunter_attempt_count"] == 0
    assert report["query_planned_count"] == 0
    assert report["suggestion_count"] == 0
    assert report["corpus_ready_for_match_evaluation"] is False


def test_readiness_separates_hunter_traffic_from_missing_shadow_suggestions():
    events = [
        _event(1, component="hunter", operation="hunt_plan"),
        _event(2, component="hunter", operation="hunt_search_wave_observed"),
        _event(
            3,
            component="search_gateway",
            operation="query_planned",
            metadata={"query_text": "query one", "query_index": 0},
        ),
        _event(4, component="hunter", operation="hunt_funnel_complete"),
    ]
    report = build_shadow_query_match_summary(events)
    assert report["corpus_state"] == "query_plans_without_shadow_suggestions"
    assert report["hunter_attempt_count"] == 1
    assert report["hunter_plan_count"] == 1
    assert report["hunter_search_wave_count"] == 1
    assert report["hunter_funnel_complete_count"] == 1
    assert report["query_planned_count"] == 1
    assert report["search_gateway_attempt_count"] == 1
    assert report["suggestion_attempt_count"] == 0
    assert report["corpus_ready_for_match_evaluation"] is False


def test_readiness_becomes_match_evaluable_when_shadow_suggestion_exists():
    events = [
        _event(1, component="hunter", operation="hunt_plan"),
        _event(
            2,
            component="search_gateway",
            operation="query_planned",
            metadata={"query_text": "query one", "query_index": 0},
        ),
        _event(
            3,
            component="search_refinement_shadow",
            operation="follow_up_query_suggested",
            metadata={
                "query_text": "query two",
                "gap_code": "sparse_yield",
                "effective_regime": "discovery",
            },
        ),
    ]
    report = build_shadow_query_match_summary(events)
    assert report["corpus_state"] == "shadow_suggestions_present"
    assert report["suggestion_attempt_count"] == 1
    assert report["suggestion_count"] == 1
    assert report["corpus_ready_for_match_evaluation"] is True


def test_readonly_inventory_reads_hunter_readiness_events(tmp_path: Path):
    db = tmp_path / "runtime.sqlite3"
    ledger = SQLiteTraceLedger(db)
    ledger.append(
        TraceEventCreate(
            mission_id="m1",
            attempt_id="a1",
            component="hunter",
            operation="hunt_plan",
            state=TraceState.SUCCEEDED,
            reason_code="hunter_query_plan_built",
            event_key="hunter-plan",
        )
    )
    ledger.append(
        TraceEventCreate(
            mission_id="m1",
            attempt_id="a1",
            component="search_gateway",
            operation="query_planned",
            state=TraceState.STARTED,
            reason_code="query_planned",
            metadata={"query_text": "query one", "query_index": 0},
            event_key="query-plan",
        )
    )

    report = build_inventory_report(db)
    assert report["corpus_state"] == "query_plans_without_shadow_suggestions"
    assert report["hunter_attempt_count"] == 1
    assert report["query_planned_count"] == 1
    assert report["suggestion_count"] == 0
