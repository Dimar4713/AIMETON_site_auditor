from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.agent_activity import ActivityBlocked, ActivityConflict, AgentActivityRepository
from app.runtime_time import RuntimeTimeSnapshot, runtime_time_snapshot
from app.temporal_orchestrator import TrustedTime

router = APIRouter(prefix="/activity", tags=["agent-activity"])


class HeartbeatRequest(BaseModel):
    mission_id: str = Field(min_length=1, max_length=128)
    agent_id: str = Field(min_length=1, max_length=128)
    state: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=256)
    idempotency_key: str = Field(min_length=1, max_length=256)


class WatchdogStatus(BaseModel):
    mission_id: str
    agent_id: str
    status: Literal["active", "stale", "blocked", "unknown"]
    state: str | None = None
    reason: str | None = None
    last_seen_at: str | None = None
    age_seconds: float | None = None
    threshold_seconds: int


def _repository() -> AgentActivityRepository:
    configured = os.getenv("AIMETON_ACTIVITY_DB", "").strip()
    if configured:
        path = Path(configured)
    else:
        runtime_db = Path(os.getenv("AIMETON_RUNTIME_DB", "data/runtime-core.sqlite3"))
        path = runtime_db.with_name("agent-activity.sqlite3")
    path.parent.mkdir(parents=True, exist_ok=True)
    return AgentActivityRepository(path)


def _trusted_time(snapshot: RuntimeTimeSnapshot | None = None) -> TrustedTime:
    value = snapshot or runtime_time_snapshot()
    parsed = datetime.fromisoformat(value.utc.replace("Z", "+00:00"))
    return TrustedTime(
        utc=parsed.astimezone(timezone.utc),
        source=value.source,
        synced=value.synced,
        quality=value.quality,
        offset_ms=value.offset_ms if value.offset_ms is not None else float("inf"),
        stratum=value.stratum if value.stratum is not None else 16,
    )


@router.post("/heartbeat", status_code=201)
def write_heartbeat(request: HeartbeatRequest) -> dict[str, object]:
    try:
        heartbeat = _repository().heartbeat(
            mission_id=request.mission_id,
            agent_id=request.agent_id,
            state=request.state,
            reason=request.reason,
            idempotency_key=request.idempotency_key,
            now=_trusted_time(),
        )
    except ActivityBlocked as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ActivityConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return asdict(heartbeat)


@router.get("/missions/{mission_id}/agents/{agent_id}/heartbeat")
def read_heartbeat(mission_id: str, agent_id: str) -> dict[str, object]:
    heartbeat = _repository().latest_heartbeat(mission_id, agent_id)
    if heartbeat is None:
        raise HTTPException(status_code=404, detail="agent_heartbeat_not_found")
    return asdict(heartbeat)


@router.get("/missions/{mission_id}/events")
def read_events(mission_id: str) -> list[dict[str, object]]:
    return [asdict(event) for event in _repository().list_events(mission_id)]


@router.get("/missions/{mission_id}/agents/{agent_id}/watchdog", response_model=WatchdogStatus)
def watchdog_status(
    mission_id: str,
    agent_id: str,
    stale_after_seconds: int = Query(default=900, ge=30, le=86400),
) -> WatchdogStatus:
    now = _trusted_time()
    if not now.trusted:
        raise HTTPException(status_code=503, detail="blocked:untrusted_time")
    heartbeat = _repository().latest_heartbeat(mission_id, agent_id)
    if heartbeat is None:
        return WatchdogStatus(
            mission_id=mission_id,
            agent_id=agent_id,
            status="unknown",
            threshold_seconds=stale_after_seconds,
        )
    last_seen = datetime.fromisoformat(heartbeat.last_seen_at.replace("Z", "+00:00"))
    age_seconds = max(0.0, (now.utc - last_seen).total_seconds())
    if heartbeat.state == "blocked":
        status: Literal["active", "stale", "blocked", "unknown"] = "blocked"
    elif age_seconds > stale_after_seconds:
        status = "stale"
    else:
        status = "active"
    return WatchdogStatus(
        mission_id=mission_id,
        agent_id=agent_id,
        status=status,
        state=heartbeat.state,
        reason=heartbeat.reason,
        last_seen_at=heartbeat.last_seen_at,
        age_seconds=age_seconds,
        threshold_seconds=stale_after_seconds,
    )
