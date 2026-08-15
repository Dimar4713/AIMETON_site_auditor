from __future__ import annotations

from datetime import UTC, datetime
from threading import RLock
from typing import Any, Literal

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel, ConfigDict

from app.external_sources import run_enriched_site_analysis
from app.mission_orchestrator import (
    EntryPoint,
    default_site_mission_request,
    get_mission_orchestrator,
    record_legacy_site_turn,
)
from app.models import AnalyzeRequest
from app.runtime_time import runtime_time_snapshot
from app.scraper import FetchError, fetch_site
from app.trace_context import bind_trace_identity
from app.umel import get_umel_event


router = APIRouter(prefix="/api/analyze", tags=["analysis-runtime"])
_LOCK = RLock()
_ANALYSES: dict[str, dict[str, Any]] = {}


class AnalysisNotFoundError(LookupError):
    """Raised when an analysis lifecycle lookup cannot resolve the requested id."""


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnalysisStartResponse(ApiModel):
    mission_id: str
    analysis_id: str
    state: Literal["queued"]
    status_url: str
    events_url: str


class AnalysisEvent(ApiModel):
    sequence: int
    timestamp: datetime
    phase: str
    event_code: str
    icon: str
    state: Literal[
        "queued",
        "running",
        "degraded",
        "blocked",
        "stalled",
        "completed",
        "failed",
    ]
    icon_key: str
    message: str
    detail: str | None = None
    heartbeat: bool = False
    next_action: str | None = None


def _canonical_now() -> datetime:
    value = runtime_time_snapshot().utc.replace("Z", "+00:00")
    return datetime.fromisoformat(value).astimezone(UTC)


def _append_event(
    analysis_id: str,
    *,
    phase: str,
    event_code: str,
    state: str,
    icon_key: str,
    message: str,
    detail: str | None = None,
    heartbeat: bool = False,
    next_action: str | None = None,
) -> None:
    umel = get_umel_event(event_code)
    if umel is None:
        raise ValueError(f"unknown_umel_event:{event_code}")
    now = _canonical_now()
    with _LOCK:
        record = _ANALYSES[analysis_id]
        events = record["events"]
        events.append(
            AnalysisEvent(
                sequence=len(events) + 1,
                timestamp=now,
                phase=phase,
                event_code=event_code,
                icon=umel.icon,
                state=state,
                icon_key=icon_key,
                message=message,
                detail=detail,
                heartbeat=heartbeat,
                next_action=next_action,
            ).model_dump(mode="json")
        )
        record["state"] = state
        record["updated_at"] = now.isoformat()


def create_analysis_runtime(
    source_url: str,
    *,
    entry_point: EntryPoint,
) -> AnalysisStartResponse:
    """Create the canonical queued analysis record without choosing a scheduler."""
    orchestrator = get_mission_orchestrator()
    mission = orchestrator.create_mission(
        default_site_mission_request(source_url),
        entry_point=entry_point,
    )
    mission_id = mission.contract.mission_id
    analysis_id = mission.contract.analysis_id
    now = _canonical_now().isoformat()
    with _LOCK:
        _ANALYSES[analysis_id] = {
            "analysis_id": analysis_id,
            "mission_id": mission_id,
            "state": "queued",
            "created_at": now,
            "updated_at": now,
            "events": [],
            "result": None,
        }
    _append_event(
        analysis_id,
        phase="mission_accepted",
        event_code="mission.received",
        state="queued",
        icon_key="inbox",
        message="Задача принята и поставлена в очередь.",
        next_action="Начать подключение к сайту.",
    )
    return AnalysisStartResponse(
        mission_id=mission_id,
        analysis_id=analysis_id,
        state="queued",
        status_url=f"/api/analyze/{analysis_id}",
        events_url=f"/api/analyze/{analysis_id}/events",
    )


def get_analysis_status_payload(analysis_id: str) -> dict[str, Any]:
    """Return a scheduler-neutral status snapshot for REST or MCP adapters."""
    with _LOCK:
        record = _ANALYSES.get(analysis_id)
        if record is None:
            raise AnalysisNotFoundError("analysis_not_found")
        return {
            "analysis_id": record["analysis_id"],
            "mission_id": record["mission_id"],
            "state": record["state"],
            "created_at": record["created_at"],
            "updated_at": record["updated_at"],
            "result": record["result"],
        }


def get_analysis_events_payload(analysis_id: str) -> list[dict[str, Any]]:
    """Return a copy of canonical UMEL-backed lifecycle events."""
    with _LOCK:
        record = _ANALYSES.get(analysis_id)
        if record is None:
            raise AnalysisNotFoundError("analysis_not_found")
        return list(record["events"])


async def run_analysis_runtime(
    *,
    source_url: str,
    mission_id: str,
    analysis_id: str,
) -> None:
    """Execute an already-created analysis using the shared runtime."""
    orchestrator = get_mission_orchestrator()
    final_url = source_url
    try:
        _append_event(
            analysis_id,
            phase="site_fetch_started",
            event_code="provider.requested",
            state="running",
            icon_key="globe",
            message="Подключаемся к сайту.",
            heartbeat=True,
            next_action="Получить доступный текст и метаданные сайта.",
        )
        page = await fetch_site(source_url)
        final_url = page["final_url"]
        _append_event(
            analysis_id,
            phase="site_fetch_completed",
            event_code="data.received",
            state="running",
            icon_key="check",
            message="Сайт получен. Восстанавливаем профиль компании.",
            next_action="Собрать профиль компании и внешние свидетельства.",
        )
        _append_event(
            analysis_id,
            phase="company_profile_started",
            event_code="picture.assembled",
            state="running",
            icon_key="building",
            message="Восстанавливаем профиль компании и коммерческий контекст.",
            heartbeat=True,
            next_action="Синтезировать evidence и AI-возможности.",
        )
        with bind_trace_identity(mission_id, analysis_id):
            result = await run_enriched_site_analysis(
                page["final_url"],
                page["title"],
                page["text"],
            )
        record_legacy_site_turn(
            orchestrator,
            mission_id,
            final_url=page["final_url"],
            succeeded=True,
        )
        with _LOCK:
            _ANALYSES[analysis_id]["result"] = result.model_copy(
                update={"mission_id": mission_id, "analysis_id": analysis_id}
            ).model_dump(mode="json")
        _append_event(
            analysis_id,
            phase="completed",
            event_code="mission.completed",
            state="completed",
            icon_key="check-circle",
            message="Анализ завершён. Результат готов.",
        )
    except (FetchError, httpx.HTTPError, ValueError):
        record_legacy_site_turn(
            orchestrator,
            mission_id,
            final_url=final_url,
            succeeded=False,
        )
        _append_event(
            analysis_id,
            phase="failed",
            event_code="mission.failed",
            state="failed",
            icon_key="alert-triangle",
            message="Анализ не завершён.",
            detail="Проверьте адрес сайта и повторите запуск.",
            next_action="Повторить анализ после проверки доступности сайта.",
        )


@router.post(
    "/start",
    response_model=AnalysisStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_analysis(req: AnalyzeRequest, background_tasks: BackgroundTasks):
    source_url = str(req.url)
    started = create_analysis_runtime(
        source_url,
        entry_point=EntryPoint.LEGACY_ADAPTER,
    )
    background_tasks.add_task(
        run_analysis_runtime,
        source_url=source_url,
        mission_id=started.mission_id,
        analysis_id=started.analysis_id,
    )
    return started


@router.get("/{analysis_id}")
def get_analysis_status(analysis_id: str):
    try:
        return get_analysis_status_payload(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail="analysis_not_found") from exc


@router.get("/{analysis_id}/events", response_model=list[AnalysisEvent])
def get_analysis_events(analysis_id: str):
    try:
        return get_analysis_events_payload(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail="analysis_not_found") from exc
