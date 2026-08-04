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
from app.scraper import FetchError, fetch_site


router = APIRouter(prefix="/api/analyze", tags=["analysis-runtime"])
_LOCK = RLock()
_ANALYSES: dict[str, dict[str, Any]] = {}


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


def _append_event(
    analysis_id: str,
    *,
    phase: str,
    state: str,
    icon_key: str,
    message: str,
    detail: str | None = None,
    heartbeat: bool = False,
    next_action: str | None = None,
) -> None:
    with _LOCK:
        record = _ANALYSES[analysis_id]
        events = record["events"]
        events.append(
            AnalysisEvent(
                sequence=len(events) + 1,
                timestamp=datetime.now(UTC),
                phase=phase,
                state=state,
                icon_key=icon_key,
                message=message,
                detail=detail,
                heartbeat=heartbeat,
                next_action=next_action,
            ).model_dump(mode="json")
        )
        record["state"] = state
        record["updated_at"] = datetime.now(UTC).isoformat()


async def _run_analysis(
    *,
    source_url: str,
    mission_id: str,
    analysis_id: str,
) -> None:
    orchestrator = get_mission_orchestrator()
    final_url = source_url
    try:
        _append_event(
            analysis_id,
            phase="site_fetch_started",
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
            state="running",
            icon_key="check",
            message="Сайт получен. Восстанавливаем профиль компании.",
            next_action="Собрать профиль компании и внешние свидетельства.",
        )
        _append_event(
            analysis_id,
            phase="company_profile_started",
            state="running",
            icon_key="building",
            message="Восстанавливаем профиль компании и коммерческий контекст.",
            heartbeat=True,
            next_action="Синтезировать evidence и AI-возможности.",
        )
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
    orchestrator = get_mission_orchestrator()
    mission = orchestrator.create_mission(
        default_site_mission_request(str(req.url)),
        entry_point=EntryPoint.LEGACY_ADAPTER,
    )
    mission_id = mission.contract.mission_id
    analysis_id = mission.contract.analysis_id
    now = datetime.now(UTC).isoformat()
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
        state="queued",
        icon_key="inbox",
        message="Задача принята и поставлена в очередь.",
        next_action="Начать подключение к сайту.",
    )
    background_tasks.add_task(
        _run_analysis,
        source_url=str(req.url),
        mission_id=mission_id,
        analysis_id=analysis_id,
    )
    return AnalysisStartResponse(
        mission_id=mission_id,
        analysis_id=analysis_id,
        state="queued",
        status_url=f"/api/analyze/{analysis_id}",
        events_url=f"/api/analyze/{analysis_id}/events",
    )


@router.get("/{analysis_id}")
def get_analysis_status(analysis_id: str):
    with _LOCK:
        record = _ANALYSES.get(analysis_id)
        if record is None:
            raise HTTPException(status_code=404, detail="analysis_not_found")
        return {
            "analysis_id": record["analysis_id"],
            "mission_id": record["mission_id"],
            "state": record["state"],
            "created_at": record["created_at"],
            "updated_at": record["updated_at"],
            "result": record["result"],
        }


@router.get("/{analysis_id}/events", response_model=list[AnalysisEvent])
def get_analysis_events(analysis_id: str):
    with _LOCK:
        record = _ANALYSES.get(analysis_id)
        if record is None:
            raise HTTPException(status_code=404, detail="analysis_not_found")
        return list(record["events"])
