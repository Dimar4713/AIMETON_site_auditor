from datetime import UTC, datetime, timedelta

from app.search_gap_shadow_action_inventory import summarize_shadow_actions
from app.trace_ledger import TraceEvent, TraceState


def _event(seq: int, action: str | None, reason: str | None) -> TraceEvent:
    metadata = {
        "routing_changed": False,
        "steering_enabled": False,
        "promotion_activated": False,
        "effective_regime": "discovery",
    }
    if action is not None:
        metadata["shadow_action"] = action
    if reason is not None:
        metadata["shadow_action_reason"] = reason
    return TraceEvent(
        event_id=f"event-{seq}",
        event_key=f"key-{seq}",
        mission_id="secret-mission",
        attempt_id="secret-attempt",
        sequence=seq,
        component="search_refinement_shadow",
        operation="refinement_observed",
        state=TraceState.SUCCEEDED,
        reason_code="shadow_refinement_persistence_observed",
        metadata=metadata,
        metadata_digest=f"digest-{seq}",
        created_at=datetime(2026, 8, 14, 14, 0, tzinfo=UTC) + timedelta(seconds=seq),
    )


def test_shadow_action_inventory_counts_and_exposes_latest_without_trace_identity():
    report = summarize_shadow_actions([
        _event(1, "continue", "shadow_continue_unresolved_gap_with_bounded_follow_up"),
        _event(2, "refine", "shadow_refine_duplicate_or_excluded_pressure"),
    ])
    assert report["shadow_action_observation_count"] == 2
    assert report["shadow_action_counts"] == {"continue": 1, "refine": 1, "skip": 0}
    assert report["latest_shadow_action"] == "refine"
    assert report["latest_shadow_action_reason"] == "shadow_refine_duplicate_or_excluded_pressure"
    assert report["latest_shadow_effective_regime"] == "discovery"
    assert report["routing_changed"] is False
    assert report["steering_enabled"] is False
    assert report["promotion_activated"] is False
    text = repr(report)
    assert "secret-mission" not in text
    assert "secret-attempt" not in text


def test_shadow_action_inventory_ignores_legacy_and_unknown_actions():
    report = summarize_shadow_actions([
        _event(1, None, None),
        _event(2, "execute", "must_not_export"),
    ])
    assert report["shadow_action_observation_count"] == 0
    assert report["latest_shadow_action"] is None
    assert report["latest_shadow_action_reason"] is None
