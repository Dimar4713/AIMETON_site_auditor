from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

import app.analysis_async_api as async_api
from app.analysis_async_api import AnalysisNotFoundError
from app.mcp_server import analysis_events, analysis_status, mcp
from app.mission_orchestrator import EntryPoint


BASE_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
    "Host": "stage-auditor.aimeton.ru",
    "Origin": "https://stage-auditor.aimeton.ru",
}

INIT_PAYLOAD = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "pytest-async-analysis", "version": "0"},
    },
}


@pytest.mark.asyncio
async def test_public_mcp_discovers_async_analysis_tools():
    mcp._session_manager = None
    app = mcp.streamable_http_app()
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            init = await client.post("/", json=INIT_PAYLOAD, headers=BASE_HEADERS)
            assert init.status_code == 200, init.text

            notification = await client.post(
                "/",
                json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                headers=BASE_HEADERS,
            )
            assert notification.status_code in {200, 202}, notification.text

            listed = await client.post(
                "/",
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                headers=BASE_HEADERS,
            )
            assert listed.status_code == 200, listed.text
            tools = {
                tool["name"]: tool
                for tool in listed.json()["result"]["tools"]
            }

    assert {
        "analyze_site",
        "analysis.start",
        "analysis.status",
        "analysis.events",
        "start_search_mission",
        "runtime.time",
        "runtime.wait.status",
        "runtime.deadline.check",
        "hunt_companies",
        "company_intelligence",
    } <= set(tools)
    assert len(tools) == 10
    assert "poll" in tools["analysis.status"]["inputSchema"]["properties"]
    assert "poll" in tools["analysis.events"]["inputSchema"]["properties"]


def test_shared_analysis_runtime_starts_queued_with_canonical_event():
    started = async_api.create_analysis_runtime(
        "https://example.com",
        entry_point=EntryPoint.MCP,
    )

    status = async_api.get_analysis_status_payload(started.analysis_id)
    events = async_api.get_analysis_events_payload(started.analysis_id)

    assert started.state == "queued"
    assert status["mission_id"] == started.mission_id
    assert status["analysis_id"] == started.analysis_id
    assert status["state"] == "queued"
    assert status["result"] is None
    assert events[0]["event_code"] == "mission.received"
    assert events[0]["state"] == "queued"


def test_unknown_analysis_id_is_explicit_and_sanitized():
    with pytest.raises(AnalysisNotFoundError, match="^analysis_not_found$"):
        async_api.get_analysis_status_payload("missing-analysis")
    with pytest.raises(AnalysisNotFoundError, match="^analysis_not_found$"):
        async_api.get_analysis_events_payload("missing-analysis")


@pytest.mark.asyncio
async def test_poll_sequence_changes_arguments_and_returns_next_poll():
    started = async_api.create_analysis_runtime(
        "https://example.com",
        entry_point=EntryPoint.MCP,
    )

    first_status = await analysis_status(started.analysis_id, poll=1)
    second_status = await analysis_status(started.analysis_id, poll=2)
    first_events = await analysis_events(started.analysis_id, poll=1)
    second_events = await analysis_events(started.analysis_id, poll=2)

    assert first_status["poll"] == 1
    assert first_status["next_poll"] == 2
    assert second_status["poll"] == 2
    assert second_status["next_poll"] == 3
    assert first_events["poll"] == 1
    assert first_events["next_poll"] == 2
    assert second_events["poll"] == 2
    assert second_events["next_poll"] == 3
    assert first_events["events"][0]["event_code"] == "mission.received"


@pytest.mark.asyncio
async def test_negative_poll_is_rejected():
    started = async_api.create_analysis_runtime(
        "https://example.com",
        entry_point=EntryPoint.MCP,
    )
    with pytest.raises(ValueError, match="^poll_must_be_non_negative$"):
        await analysis_status(started.analysis_id, poll=-1)
    with pytest.raises(ValueError, match="^poll_must_be_non_negative$"):
        await analysis_events(started.analysis_id, poll=-1)


@pytest.mark.asyncio
async def test_mcp_scheduler_keeps_task_alive_until_completion(monkeypatch):
    finished = asyncio.Event()
    observed: dict[str, str] = {}

    async def fake_run_analysis(*, source_url: str, mission_id: str, analysis_id: str) -> None:
        observed.update(
            source_url=source_url,
            mission_id=mission_id,
            analysis_id=analysis_id,
        )
        finished.set()

    monkeypatch.setattr(async_api, "_run_analysis", fake_run_analysis)
    started = async_api.create_analysis_runtime(
        "https://example.com",
        entry_point=EntryPoint.MCP,
    )

    async_api.schedule_analysis_runtime(
        source_url="https://example.com",
        mission_id=started.mission_id,
        analysis_id=started.analysis_id,
    )
    await asyncio.wait_for(finished.wait(), timeout=1)
    await asyncio.sleep(0)

    assert observed == {
        "source_url": "https://example.com",
        "mission_id": started.mission_id,
        "analysis_id": started.analysis_id,
    }
