#!/usr/bin/env python3
from __future__ import annotations

import json
import time
from typing import Any
from urllib.request import Request, urlopen

URL = "https://stage-auditor.aimeton.ru/mcp/"
ORIGIN = "chrome-extension://aabiopennjmopfippagcalmkdjlepdhh"
PROTOCOL_VERSION = "2025-06-18"
TARGET = "https://aimeton.ru"
REQUEST_TIMEOUT = 25
MISSION_DEADLINE = 225
POLL_SECONDS = 4


def decode(body: bytes, content_type: str) -> dict[str, Any]:
    text = body.decode("utf-8")
    if "text/event-stream" in content_type:
        lines = [line[5:].strip() for line in text.splitlines() if line.startswith("data:")]
        assert lines, text
        text = lines[-1]
    payload = json.loads(text)
    assert isinstance(payload, dict), payload
    return payload


def post(message: dict[str, Any], session_id: str | None = None) -> tuple[dict[str, Any] | None, str | None, float]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": PROTOCOL_VERSION,
        "Origin": ORIGIN,
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    req = Request(
        URL,
        data=json.dumps(message, separators=(",", ":")).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    started = time.monotonic()
    with urlopen(req, timeout=REQUEST_TIMEOUT) as response:
        elapsed = time.monotonic() - started
        assert response.headers.get("Access-Control-Allow-Origin") == ORIGIN, dict(response.headers)
        sid = response.headers.get("Mcp-Session-Id") or session_id
        body = response.read()
        return (decode(body, response.headers.get("Content-Type", "")) if body else None), sid, elapsed


def rpc_result(response: dict[str, Any] | None) -> Any:
    assert response is not None
    assert "error" not in response, response
    return response["result"]


def tool_payload(call_result: dict[str, Any]) -> dict[str, Any]:
    assert call_result.get("isError") is not True, call_result
    structured = call_result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    for item in call_result.get("content", []):
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            parsed = json.loads(item["text"])
            if isinstance(parsed, dict):
                return parsed
    raise AssertionError(call_result)


def call(tool: str, args: dict[str, Any], request_id: int, session_id: str | None) -> tuple[dict[str, Any], float]:
    response, _, elapsed = post(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": tool, "arguments": args},
        },
        session_id,
    )
    return tool_payload(rpc_result(response)), elapsed


def main() -> None:
    init, session_id, initialize_seconds = post(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "aimeton-bds-live-progress-acceptance", "version": "1"},
            },
        }
    )
    rpc_result(init)
    post({"jsonrpc": "2.0", "method": "notifications/initialized"}, session_id)
    listed, _, list_seconds = post(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, session_id
    )
    names = {item["name"] for item in rpc_result(listed).get("tools", [])}
    assert {"analysis.start", "analysis.status", "analysis.events"} <= names, sorted(names)

    start, start_seconds = call("analysis.start", {"url": TARGET}, 3, session_id)
    assert start["state"] == "queued", start
    analysis_id = start["analysis_id"]
    mission_id = start["mission_id"]
    poll = int(start["next_poll"])
    request_id = 4
    started_at = time.monotonic()
    deadline = started_at + MISSION_DEADLINE

    observed_progress = False
    observed_active_provider = False
    observed_heartbeat = False
    observed_stalled = False
    observed_degraded = False
    max_queries_planned = 0
    max_queries_finished = 0
    snapshots: list[dict[str, Any]] = []
    last_status: dict[str, Any] = {}
    last_events: dict[str, Any] = {}

    while time.monotonic() < deadline:
        last_status, status_seconds = call(
            "analysis.status",
            {"analysis_id": analysis_id, "poll": poll},
            request_id,
            session_id,
        )
        request_id += 1
        last_events, events_seconds = call(
            "analysis.events",
            {"analysis_id": analysis_id, "poll": poll},
            request_id,
            session_id,
        )
        request_id += 1
        assert status_seconds < REQUEST_TIMEOUT
        assert events_seconds < REQUEST_TIMEOUT
        assert last_status["next_poll"] == poll + 1
        assert last_events["next_poll"] == poll + 1

        progress = last_status.get("progress") or {}
        planned = int(progress.get("queries_planned") or 0)
        finished = int(progress.get("queries_finished") or 0)
        active = progress.get("active_provider_calls") or []
        max_queries_planned = max(max_queries_planned, planned)
        max_queries_finished = max(max_queries_finished, finished)
        observed_progress = observed_progress or planned > 0 or finished > 0
        observed_active_provider = observed_active_provider or bool(active)

        events = last_events.get("events") or []
        codes = {event.get("event_code") for event in events}
        states = {event.get("state") for event in events}
        observed_heartbeat = observed_heartbeat or "external.waiting" in codes
        observed_stalled = observed_stalled or "stalled" in states or "flow.gap_detected" in codes
        observed_degraded = observed_degraded or "service.degraded" in codes

        snapshots.append(
            {
                "poll": poll,
                "elapsed_s": round(time.monotonic() - started_at, 1),
                "state": last_status.get("state"),
                "phase": last_status.get("phase"),
                "queries": f"{finished}/{planned}",
                "active": active[:4],
                "event_count": last_events.get("event_count"),
                "status_s": round(status_seconds, 3),
                "events_s": round(events_seconds, 3),
            }
        )

        if last_status.get("state") in {"completed", "failed"}:
            break
        poll += 1
        time.sleep(POLL_SECONDS)

    elapsed_total = time.monotonic() - started_at
    evidence = {
        "endpoint": URL,
        "origin": ORIGIN,
        "target": TARGET,
        "mission_id": mission_id,
        "analysis_id": analysis_id,
        "initialize_seconds": round(initialize_seconds, 3),
        "list_seconds": round(list_seconds, 3),
        "analysis_start_seconds": round(start_seconds, 3),
        "mission_elapsed_seconds": round(elapsed_total, 1),
        "final_state": last_status.get("state"),
        "final_phase": last_status.get("phase"),
        "result_present": last_status.get("result") is not None,
        "observed_progress": observed_progress,
        "observed_active_provider": observed_active_provider,
        "observed_heartbeat": observed_heartbeat,
        "observed_stalled": observed_stalled,
        "observed_degraded": observed_degraded,
        "max_queries_planned": max_queries_planned,
        "max_queries_finished": max_queries_finished,
        "final_progress": last_status.get("progress"),
        "snapshots": snapshots,
    }
    print(json.dumps(evidence, ensure_ascii=False, indent=2))

    assert last_status.get("state") == "completed", evidence
    assert last_status.get("result") is not None, evidence
    assert observed_progress, evidence
    assert max_queries_planned > 0, evidence
    # A mission that lasts beyond one heartbeat interval must visibly report life.
    if elapsed_total >= 20:
        assert observed_heartbeat or observed_stalled or observed_degraded, evidence


if __name__ == "__main__":
    main()
