from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable


DEFAULT_STALL_AFTER_SECONDS = 90


@dataclass(frozen=True)
class MissionRuntimeObservation:
    last_event_at: str | None
    heartbeat_status: str
    stalled: bool
    reason_code: str | None


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def derive_runtime_observation(
    records: Iterable[dict[str, Any]],
    *,
    now: datetime | None = None,
    stall_after_seconds: int = DEFAULT_STALL_AFTER_SECONDS,
) -> MissionRuntimeObservation:
    """Derive a bounded, server-owned heartbeat/stalled projection.

    The calculation uses only persisted sanitized event metadata. It does not
    inspect prompts, provider payloads, secrets, or chain-of-thought.
    """
    if stall_after_seconds <= 0:
        raise ValueError("stall_after_seconds must be positive")

    latest_record: dict[str, Any] | None = None
    latest_at: datetime | None = None
    for record in records:
        created_at = _parse_timestamp(record.get("created_at"))
        if created_at is None:
            continue
        if latest_at is None or created_at > latest_at:
            latest_at = created_at
            latest_record = record

    if latest_record is None or latest_at is None:
        return MissionRuntimeObservation(None, "missing", False, "heartbeat_missing")

    payload = latest_record.get("payload")
    data = payload if isinstance(payload, dict) else {}
    status = str(data.get("status", "")).lower()
    last_event_at = latest_at.isoformat()

    if status != "running":
        return MissionRuntimeObservation(last_event_at, "not_applicable", False, None)

    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    age_seconds = max(0.0, (current - latest_at).total_seconds())
    if age_seconds > stall_after_seconds:
        return MissionRuntimeObservation(last_event_at, "stalled", True, "heartbeat_stalled")
    return MissionRuntimeObservation(last_event_at, "fresh", False, None)
