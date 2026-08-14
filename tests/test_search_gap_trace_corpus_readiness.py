from datetime import UTC, datetime, timedelta
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
    counters: dict[str, int] | None = None,
    created_at: datetime | None = None,
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
        counters=counters or {},
        metadata=metadata or {},
        metadata_digest=f"digest-{seq}-{component}-{operation}",
        created_at=created_at or datetime.now(UTC),
    )


def test_readiness_reports_no_hunter_traffic_without_overclaiming():
    report = build_shadow_query_match_summary([])
    assert report["corpus_state"] == "no_hunter_traffic"
    assert report["hunter_attempt_count"] == 0
    assert report["hunter_first_at"] is None
    assert report["hunter_latest_at"] is None
    assert report["query_planned_count"] == 0
    assert report["query_first_at"] is None
    assert report["query_latest_at"] is None
    assert report["refinement_observation_count"] == 0
    assert report["suggestion_persistence_complete"] is None
    assert report["suggestion_count"] == 0
    assert report["suggestion_first_at"] is None
    assert report["suggestion_latest_at"] is None
    assert report["corpus_ready_for_match_evaluation"] is False


def test_readiness_separates_hunter_traffic_from_missing_shadow_suggestions():
    started = datetime(2026, 8, 14, 6, 0, tzinfo=UTC)
    events = [
        _event(1, component="hunter", operation="hunt_plan", created_at=started),
        _event(
            2,
            component="hunter",
            operation="hunt_search_wave_observed",
            created_at=started + timedelta(seconds=1),
        ),
        _event(
            3,
            component="search_gateway",
            operation="query_planned",
            metadata={"query_text": "query one", "query_index": 0},
            created_at=started + timedelta(seconds=2),
        ),
        _event(
            4,
            component="hunter",
            operation="hunt_funnel_complete",
            created_at=started + timedelta(seconds=3),
        ),
    ]
    report = build_shadow_query_match_summary(events)
    assert report["corpus_state"] == "query_plans_without_shadow_suggestions"
    assert report["hunter_attempt_count"] == 1
    assert report["hunter_plan_count"] == 1
    assert report["hunter_search_wave_count"] == 1
    assert report["hunter_funnel_complete_count"] == 1
    assert report["hunter_first_at"] == started.isoformat()
    assert report["hunter_latest_at"] == started.isoformat()
    assert report["query_planned_count"] == 1
    assert report["search_gateway_attempt_count"] == 1
    assert report["query_first_at"] == (started + timedelta(seconds=2)).isoformat()
    assert report["query_latest_at"] == (started + timedelta(seconds=2)).isoformat()
    assert report["suggestion_attempt_count"] == 0
    assert report["suggestion_latest_at"] is None
    assert report["corpus_ready_for_match_evaluation"] is False


def test_aggregate_refinement_observation_distinguishes_generated_from_persisted():
    started = datetime(2026, 8, 14, 6, 10, tzinfo=UTC)
    events = [
        _event(1, component="hunter", operation="hunt_plan", created_at=started),
        _event(
            2,
            component="search_gateway",
            operation="query_planned",
            metadata={"query_text": "query one", "query_index": 0},
            created_at=started + timedelta(seconds=1),
        ),
        _event(
            3,
            component="search_refinement_shadow",
            operation="refinement_observed",
            counters={
                "gap_count": 2,
                "suggestion_count": 3,
                "persisted_suggestion_count": 2,
            },
            created_at=started + timedelta(seconds=2),
        ),
    ]
    report = build_shadow_query_match_summary(events)
    assert report["refinement_observation_count"] == 1
    assert report["refinement_observation_attempt_count"] == 1
    assert report["refinement_first_at"] == (started + timedelta(seconds=2)).isoformat()
    assert report["refinement_latest_at"] == (started + timedelta(seconds=2)).isoformat()
    assert report["observed_gap_count"] == 2
    assert report["observed_suggestion_count"] == 3
    assert report["persisted_suggestion_count"] == 2
    assert report["suggestion_persistence_complete"] is False


def test_readiness_becomes_match_evaluable_when_shadow_suggestion_exists():
    started = datetime(2026, 8, 14, 6, 0, tzinfo=UTC)
    events = [
        _event(1, component="hunter", operation="hunt_plan", created_at=started),
        _event(
            2,
            component="search_gateway",
            operation="query_planned",
            metadata={"query_text": "query one", "query_index": 0},
            created_at=started + timedelta(seconds=1),
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
            created_at=started + timedelta(seconds=2),
        ),
    ]
    report = build_shadow_query_match_summary(events)
    assert report["corpus_state"] == "shadow_suggestions_present"
    assert report["suggestion_attempt_count"] == 1
    assert report["suggestion_count"] == 1
    assert report["suggestion_first_at"] == (started + timedelta(seconds=2)).isoformat()
    assert report["suggestion_latest_at"] == (started + timedelta(seconds=2)).isoformat()
    assert report["corpus_ready_for_match_evaluation"] is True


def test_readonly_inventory_reads_hunter_and_refinement_readiness_events(tmp_path: Path):
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
    ledger.append(
        TraceEventCreate(
            mission_id="m1",
            attempt_id="a1",
            component="search_refinement_shadow",
            operation="refinement_observed",
            state=TraceState.SUCCEEDED,
            reason_code="shadow_refinement_persistence_observed",
            counters={
                "gap_count": 1,
                "suggestion_count": 0,
                "persisted_suggestion_count": 0,
            },
            event_key="refinement-observed",
        )
    )

    report = build_inventory_report(db)
    assert report["corpus_state"] == "query_plans_without_shadow_suggestions"
    assert report["hunter_attempt_count"] == 1
    assert report["hunter_latest_at"] is not None
    assert report["query_planned_count"] == 1
    assert report["query_latest_at"] is not None
    assert report["refinement_observation_count"] == 1
    assert report["observed_gap_count"] == 1
    assert report["observed_suggestion_count"] == 0
    assert report["persisted_suggestion_count"] == 0
    assert report["suggestion_persistence_complete"] is True
    assert report["suggestion_count"] == 0
