from pathlib import Path

from app.models import HuntResult
from app.search_gap_shadow_refinement import (
    FollowUpQuerySuggestion,
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


def test_shadow_follow_up_suggestion_is_retained_as_trace_only_evidence(tmp_path: Path):
    db = tmp_path / "runtime.sqlite3"
    plan = ShadowRefinementPlan(
        gaps=(),
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
    assert len(events) == 1
    event = events[0]
    assert event.component == "search_refinement_shadow"
    assert event.operation == "follow_up_query_suggested"
    assert event.reason_code == "sparse_yield"
    assert event.retention_class is RetentionClass.TRACE
    assert event.metadata["query_text"] == "стоматология Красноярск официальный сайт"
    assert event.metadata["gap_code"] == "sparse_yield"
    assert event.metadata["effective_regime"] == "discovery"
    assert event.metadata["routing_changed"] is False
    assert event.metadata["steering_enabled"] is False


def test_empty_shadow_plan_writes_nothing(tmp_path: Path):
    db = tmp_path / "runtime.sqlite3"
    persisted = persist_shadow_follow_up_suggestions(
        mission_id="hunt-shadow-trace",
        attempt_id="corr-shadow-trace",
        effective_regime="balanced",
        plan=ShadowRefinementPlan(gaps=(), suggestions=()),
        trace_db_path=db,
    )
    assert persisted == 0
    assert not db.exists()
