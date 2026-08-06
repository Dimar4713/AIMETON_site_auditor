from __future__ import annotations

import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from app.runtime_time import RuntimeTimeSnapshot, runtime_time_snapshot
from app.temporal_orchestrator import TrustedTime, evaluate_temporal_intent
from app.temporal_repository import TemporalIntentRepository


def temporal_repository_path() -> Path:
    value = os.getenv("AIMETON_TEMPORAL_DB_PATH", "/app/data/temporal-intents.sqlite3").strip()
    path = Path(value)
    if not path.is_absolute():
        raise ValueError("AIMETON_TEMPORAL_DB_PATH must be absolute")
    return path


def wait_status_payload(wait_id: str, *, repository: TemporalIntentRepository | None = None) -> dict:
    repo = repository or TemporalIntentRepository(temporal_repository_path())
    intent = repo.get(wait_id)
    if intent is None:
        return {"wait_id": wait_id, "found": False, "status": "not_found", "read_only": True}
    payload = asdict(intent)
    for key in ("created_at", "resume_not_before", "deadline"):
        payload[key] = _utc_z(payload[key])
    payload["timeout_action"] = intent.timeout_action.value
    return {"wait_id": wait_id, "found": True, "intent": payload, "read_only": True}


def deadline_check_payload(
    wait_id: str,
    *,
    repository: TemporalIntentRepository | None = None,
    snapshot: RuntimeTimeSnapshot | None = None,
) -> dict:
    repo = repository or TemporalIntentRepository(temporal_repository_path())
    intent = repo.get(wait_id)
    if intent is None:
        return {
            "wait_id": wait_id,
            "found": False,
            "state": "blocked",
            "reason": "blocked:intent_not_found",
            "read_only": True,
        }
    time_snapshot = snapshot or runtime_time_snapshot()
    trusted_time = TrustedTime(
        utc=datetime.fromisoformat(time_snapshot.utc.replace("Z", "+00:00")),
        source=time_snapshot.source,
        synced=time_snapshot.synced,
        quality=time_snapshot.quality,
        offset_ms=float(time_snapshot.offset_ms or 0.0),
        stratum=int(time_snapshot.stratum or 16),
    )
    decision = evaluate_temporal_intent(intent, trusted_time)
    return {
        "wait_id": wait_id,
        "found": True,
        "state": decision.state.value,
        "reason": decision.reason,
        "evaluated_at": _utc_z(decision.evaluated_at),
        "next_check_at": None if decision.next_check_at is None else _utc_z(decision.next_check_at),
        "time_source": time_snapshot.source,
        "time_quality": time_snapshot.quality,
        "read_only": True,
    }


def _utc_z(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
