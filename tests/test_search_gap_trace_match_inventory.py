from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

from app.search_gap_trace_match_inventory import (
    build_shadow_query_match_summary,
    find_shadow_query_matches,
)
from app.trace_ledger import SQLiteTraceLedger, TraceEvent, TraceEventCreate, TraceState
from scripts.search_gap_trace_match_inventory import build_inventory_report


def _event(
    seq: int,
    *,
    mission: str,
    attempt: str,
    component: str,
    operation: str,
    metadata: dict,
    reason: str = "test",
) -> TraceEvent:
    return TraceEvent(
        event_id=f"event-{mission}-{attempt}-{seq}-{component}",
        event_key=f"key-{mission}-{attempt}-{seq}-{component}",
        mission_id=mission,
        attempt_id=attempt,
        sequence=seq,
        component=component,
        operation=operation,
        state=TraceState.SUCCEEDED,
        reason_code=reason,
        metadata=metadata,
        metadata_digest=f"digest-{mission}-{attempt}-{seq}-{component}",
        created_at=datetime.now(UTC),
    )


def test_inventory_separates_causal_historical_and_prior_exact_matches():
    events = [
        _event(
            2,
            mission="m1",
            attempt="a1",
            component="search_refinement_shadow",
            operation="follow_up_query_suggested",
            reason="sparse_yield",
            metadata={
                "query_text": "  Query   One ",
                "gap_code": "sparse_yield",
                "effective_regime": "discovery",
            },
        ),
        _event(
            1,
            mission="m1",
            attempt="a1",
            component="search_gateway",
            operation="query_planned",
            metadata={"query_text": "query one", "query_index": 1},
        ),
        _event(
            3,
            mission="m1",
            attempt="a1",
            component="search_gateway",
            operation="query_planned",
            metadata={"query_text": "QUERY ONE", "query_index": 2},
        ),
        _event(
            1,
            mission="m2",
            attempt="a2",
            component="search_gateway",
            operation="query_planned",
            metadata={"query_text": "query one", "query_index": 8},
        ),
    ]

    matches = find_shadow_query_matches(events)
    assert {match.kind for match in matches} == {
        "same_attempt_causal_candidate",
        "historical_noncausal_candidate",
        "same_attempt_prior_collision",
    }
    summary = build_shadow_query_match_summary(events)
    assert summary["suggestion_count"] == 1
    assert summary["matched_suggestion_count"] == 1
    assert summary["unmatched_suggestion_count"] == 0
    assert summary["same_attempt_causal_candidate_count"] == 1
    assert summary["historical_noncausal_candidate_count"] == 1
    assert summary["same_attempt_prior_collision_count"] == 1
    bucket = summary["buckets"]["discovery:sparse_yield"]
    assert bucket == {
        "suggestions": 1,
        "same_attempt_causal_candidates": 1,
        "historical_noncausal_candidates": 1,
        "same_attempt_prior_collisions": 1,
    }
    serialized = json.dumps(summary, ensure_ascii=False)
    assert "Query One" not in serialized
    assert "query one" not in serialized
    assert "m1" not in serialized
    assert "a1" not in serialized


def test_unmatched_suggestion_remains_explicit_without_promotion():
    events = [
        _event(
            1,
            mission="m1",
            attempt="a1",
            component="search_refinement_shadow",
            operation="follow_up_query_suggested",
            reason="region_confirmation_missing",
            metadata={
                "query_text": "dentistry region evidence",
                "gap_code": "region_confirmation_missing",
                "effective_regime": "balanced",
            },
        )
    ]
    summary = build_shadow_query_match_summary(events)
    assert summary["suggestion_count"] == 1
    assert summary["matched_suggestion_count"] == 0
    assert summary["unmatched_suggestion_count"] == 1
    assert summary["promotion_activated"] is False
    assert summary["routing_changed"] is False
    assert summary["steering_enabled"] is False


def test_inventory_cli_reads_existing_db_without_mutable_ledger_init(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    db = tmp_path / "runtime.sqlite3"
    ledger = SQLiteTraceLedger(db)
    for event in (
        TraceEventCreate(
            mission_id="m1",
            attempt_id="a1",
            component="search_refinement_shadow",
            operation="follow_up_query_suggested",
            state=TraceState.SUCCEEDED,
            reason_code="sparse_yield",
            metadata={
                "query_text": "query one",
                "gap_code": "sparse_yield",
                "effective_regime": "discovery",
            },
            event_key="suggestion",
        ),
        TraceEventCreate(
            mission_id="m2",
            attempt_id="a2",
            component="search_gateway",
            operation="query_planned",
            state=TraceState.STARTED,
            reason_code="query_planned",
            metadata={"query_text": "query one", "query_index": 5},
            event_key="planned",
        ),
    ):
        ledger.append(event)

    def mutable_init_must_not_run(*_args, **_kwargs):
        raise AssertionError("mutable SQLiteTraceLedger initialization is forbidden")

    monkeypatch.setattr(SQLiteTraceLedger, "__init__", mutable_init_must_not_run)
    report = build_inventory_report(db)
    assert report["suggestion_count"] == 1
    assert report["historical_noncausal_candidate_count"] == 1
