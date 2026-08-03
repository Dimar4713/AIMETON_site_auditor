from __future__ import annotations

from app.mission_checkpoint import MissionCheckpoint
from app.runtime_core.models import EventCreate
from app.runtime_core.storage import RuntimeStore

CHECKPOINT_EVENT_TYPE = "mission.checkpoint"


def save_checkpoint(
    store: RuntimeStore,
    *,
    task_id: str,
    checkpoint: MissionCheckpoint,
    actor_ref: str,
    mandate_ref: str,
    correlation_id: str,
) -> MissionCheckpoint:
    """Persist a sanitized checkpoint through the existing Runtime Core event store."""
    existing = latest_checkpoint(store, task_id=task_id)
    if existing is not None:
        if existing.sequence > checkpoint.sequence:
            raise ValueError("checkpoint sequence cannot move backwards")
        if existing.sequence == checkpoint.sequence:
            if existing.state_digest == checkpoint.state_digest:
                return existing
            raise ValueError("checkpoint conflict at persisted sequence")

    store.append_event(
        task_id,
        EventCreate(
            actor_ref=actor_ref,
            mandate_ref=mandate_ref,
            event_type=CHECKPOINT_EVENT_TYPE,
            reason="Persist sanitized mission checkpoint",
            payload={"checkpoint": checkpoint.model_dump(mode="json")},
            correlation_id=correlation_id,
        ),
    )
    return checkpoint


def latest_checkpoint(store: RuntimeStore, *, task_id: str) -> MissionCheckpoint | None:
    latest: MissionCheckpoint | None = None
    for item in store.records(task_id):
        if item["kind"] != "event":
            continue
        record = item["record"]
        if record.get("event_type") != CHECKPOINT_EVENT_TYPE:
            continue
        payload = record.get("payload") or {}
        raw = payload.get("checkpoint")
        if not isinstance(raw, dict):
            continue
        candidate = MissionCheckpoint.model_validate(raw)
        if latest is None or candidate.sequence > latest.sequence:
            latest = candidate
    return latest
