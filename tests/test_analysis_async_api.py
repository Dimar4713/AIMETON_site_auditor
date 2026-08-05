import asyncio

from fastapi import BackgroundTasks

from app.analysis_async_api import (
    get_analysis_events,
    get_analysis_status,
    start_analysis,
)
from app.mission_orchestrator import reset_mission_orchestrator
from app.models import AnalyzeRequest


def setup_function() -> None:
    reset_mission_orchestrator()


def test_start_returns_immediate_identifiers_and_relative_urls() -> None:
    background_tasks = BackgroundTasks()

    response = asyncio.run(
        start_analysis(
            AnalyzeRequest(url="https://example.com"),
            background_tasks,
        )
    )

    assert response.state == "queued"
    assert response.mission_id.startswith("mission_")
    assert response.analysis_id.startswith("analysis_")
    assert response.status_url == f"/api/analyze/{response.analysis_id}"
    assert response.events_url == f"/api/analyze/{response.analysis_id}/events"
    assert len(background_tasks.tasks) == 1

    status = get_analysis_status(response.analysis_id)
    assert status["mission_id"] == response.mission_id
    assert status["state"] == "queued"
    assert status["result"] is None


def test_initial_event_is_sanitized_actionable_and_umel_canonical() -> None:
    background_tasks = BackgroundTasks()
    response = asyncio.run(
        start_analysis(
            AnalyzeRequest(url="https://example.com"),
            background_tasks,
        )
    )

    events = get_analysis_events(response.analysis_id)

    assert len(events) == 1
    event = events[0]
    assert event["phase"] == "mission_accepted"
    assert event["event_code"] == "mission.received"
    assert event["icon"] == "🧭"
    assert event["icon_key"] == "inbox"
    assert event["state"] == "queued"
    assert event["message"] == "Задача принята и поставлена в очередь."
    assert event["next_action"] == "Начать подключение к сайту."
    assert event["timestamp"].endswith("+00:00")
    serialized = str(event).lower()
    assert "secret" not in serialized
    assert "prompt" not in serialized
    assert "chain-of-thought" not in serialized
