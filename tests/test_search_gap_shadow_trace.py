from pathlib import Path

from app.models import HuntResult
from app.search_gap_shadow_refinement import (
    FollowUpQuerySuggestion,
    SearchGapObservation,
    ShadowRefinementPlan,
)
from app.search_gap_shadow_trace import persist_shadow_follow_up_suggestions
from app.trace_ledger import RetentionClass, SQLiteTraceLedger


def test_hunt_result_trace_identity_is_excluded_from_public_dump():
    result = HuntResult(
        region="Красноярск",
        discovered=0,
        trace_mission_id="hunt-secret-trace-id",
        trace_attempt_id="corr-secret-trace-id",
    )
    payload = result.model_dump(mode="json")
    assert "trace_mission_id" not in payload
    assert "trace_attempt_id" not in payload


def test_shadow_follow_up_suggestion_and_aggregate_outcome_are_retained(tmp_path: Path):
    db = tmp_path / "runtime.sqlite3"
    plan = ShadowRefinementPlan(
        gaps=(
            SearchGapObservation(
                code="sparse_yield",
                evidence_target="more_unique_candidates",
                reason="test sparse gap",
            ),
        ),
        suggestions=(
            FollowUpQuerySuggestion(
                query="стоматология Красноярск официальный сайт",
                reason_code="sparse_yield",
                evidence_target="more_unique_candidates",
            ),
        ),
    )

    persisted = persist_shadow_follow_up_suggestions(
        mission_id="hunt-shadow-trace",
        attempt_id="corr-shadow-trace",
        effective_regime="discovery",
        plan=plan,
        trace_db_path=db,
    )

    assert persisted == 1
    events = SQLiteTraceLedger(db).list_attempt("hunt-shadow-trace", "corr-shadow-trace")
    assert len(events) == 2
    suggestion = next(event for event in events if event.operation == "follow_up_query_suggested")
    assert suggestion.component == "search_refinement_shadow"
    assert suggestion.reason_code == "sparse_yield"
    assert suggestion.retention_class is RetentionClass.TRACE
    assert suggestion.metadata["query_text"] == "стоматология Красноярск официальный сайт"
    assert suggestion.metadata["gap_code"] == "sparse_yield"
    assert suggestion.metadata["effective_regime"] == "discovery"
    assert suggestion.metadata["routing_changed"] is False
    assert suggestion.metadata["steering_enabled"] is False

    observation = next(event for event in events if event.operation == "refinement_observed")
    assert observation.component == "search_refinement_shadow"
    assert observation.retention_class is RetentionClass.TRACE
    assert observation.counters == {
        "gap_count": 1,
        "suggestion_count": 1,
        "persisted_suggestion_count": 1,
    }
    assert observation.metadata["effective_regime"] == "discovery"
    assert observation.metadata["shadow_action"] == "continue"
    assert observation.metadata["shadow_action_reason"] == (
        "shadow_continue_unresolved_gap_with_bounded_follow_up"
    )
    assert observation.metadata["routing_changed"] is False
    assert observation.metadata["steering_enabled"] is False
    assert observation.metadata["promotion_activated"] is False
    assert "query_text" not in observation.metadata


def test_empty_shadow_plan_still_records_decisive_aggregate_observation(tmp_path: Path):
    db = tmp_path / "runtime.sqlite3"
    persisted = persist_shadow_follow_up_suggestions(
        mission_id="hunt-shadow-trace",
        attempt_id="corr-shadow-trace",
        effective_regime="balanced",
        plan=ShadowRefinementPlan(gaps=(), suggestions=()),
        trace_db_path=db,
    )
    assert persisted == 0
    events = SQLiteTraceLedger(db).list_attempt("hunt-shadow-trace", "corr-shadow-trace")
    assert len(events) == 1
    observation = events[0]
    assert observation.operation == "refinement_observed"
    assert observation.counters == {
        "gap_count": 0,
        "suggestion_count": 0,
        "persisted_suggestion_count": 0,
    }
    assert observation.metadata["shadow_action"] == "skip"
    assert observation.metadata["shadow_action_reason"] == "shadow_no_bounded_follow_up_available"
    assert observation.metadata["routing_changed"] is False
    assert observation.metadata["steering_enabled"] is False
    assert observation.metadata["promotion_activated"] is False
    assert "query_text" not in observation.metadata
