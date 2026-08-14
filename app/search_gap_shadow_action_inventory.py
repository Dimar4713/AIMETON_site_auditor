from __future__ import annotations

from collections import Counter

from app.trace_ledger import TraceEvent

_ALLOWED_ACTIONS = {"continue", "refine", "skip"}


def summarize_shadow_actions(events: list[TraceEvent]) -> dict[str, object]:
    observations = [
        event
        for event in events
        if event.component == "search_refinement_shadow"
        and event.operation == "refinement_observed"
    ]
    decided = [
        event
        for event in observations
        if str(event.metadata.get("shadow_action") or "") in _ALLOWED_ACTIONS
    ]
    counts = Counter(str(event.metadata["shadow_action"]) for event in decided)
    latest = max(decided, key=lambda event: (event.created_at, event.sequence)) if decided else None
    return {
        "shadow_action_observation_count": len(decided),
        "shadow_action_counts": {
            action: counts.get(action, 0)
            for action in ("continue", "refine", "skip")
        },
        "latest_shadow_action": (
            str(latest.metadata.get("shadow_action")) if latest is not None else None
        ),
        "latest_shadow_action_reason": (
            str(latest.metadata.get("shadow_action_reason")) if latest is not None else None
        ),
        "latest_shadow_effective_regime": (
            str(latest.metadata.get("effective_regime")) if latest is not None else None
        ),
        "routing_changed": False,
        "steering_enabled": False,
        "promotion_activated": False,
    }
