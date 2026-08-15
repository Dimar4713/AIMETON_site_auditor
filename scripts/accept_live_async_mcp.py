#!/usr/bin/env python3
from __future__ import annotations

import json
import time
from typing import Any
from urllib.request import Request, urlopen

URL = "https://stage-auditor.aimeton.ru/mcp/"
ORIGIN = "chrome-extension://aabiopennjmopfippagcalmkdjlepdhh"
PROTOCOL_VERSION = "2025-06-18"


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
    request = Request(
        URL,
        data=json.dumps(message, separators=(",", ":")).encode(),
        headers=headers,
        method="POST",
    )
    started = time.monotonic()
    with urlopen(request, timeout=25) as response:
        elapsed = time.monotonic() - started
        assert response.headers.get("Access-Control-Allow-Origin") == ORIGIN, dict(response.headers)
        sid = response.headers.get("Mcp-Session-Id") or session_id
        body = response.read()
        return (decode(body, response.headers.get("Content-Type", "")) if body else None), sid, elapsed


def result(response: dict[str, Any] | None) -> Any:
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
    return tool_payload(result(response)), elapsed


def main() -> None:
    init, session_id, init_elapsed = post(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "aimeton-bds-async-live-acceptance", "version": "1"},
            },
        }
    )
    result(init)
    post({"jsonrpc": "2.0", "method": "notifications/initialized"}, session_id)
    listed, _, list_elapsed = post(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, session_id
    )
    tools = result(listed).get("tools", [])
    names = {item["name"] for item in tools}
    expected = {"analysis.start", "analysis.status", "analysis.events"}
    assert expected <= names, sorted(names)
    assert len(names) == 10, sorted(names)

    start_payload, start_elapsed = call(
        "analysis.start", {"url": "https://aimeton.ru"}, 3, session_id
    )
    assert start_payload["state"] == "queued", start_payload
    assert start_payload["next_poll"] == 1, start_payload
    analysis_id = start_payload["analysis_id"]
    mission_id = start_payload["mission_id"]
    assert start_elapsed < 25, start_elapsed

    poll = int(start_payload["next_poll"])
    last_status: dict[str, Any] = {}
    last_events: dict[str, Any] = {}
    timings: list[dict[str, Any]] = []
    deadline = time.monotonic() + 90
    request_id = 4
    while time.monotonic() < deadline:
        last_status, status_elapsed = call(
            "analysis.status", {"analysis_id": analysis_id, "poll": poll}, request_id, session_id
        )
        request_id += 1
        assert last_status["poll"] == poll, last_status
        assert last_status["next_poll"] == poll + 1, last_status
        assert status_elapsed < 25, status_elapsed

        last_events, events_elapsed = call(
            "analysis.events", {"analysis_id": analysis_id, "poll": poll}, request_id, session_id
        )
        request_id += 1
        assert last_events["poll"] == poll, last_events
        assert last_events["next_poll"] == poll + 1, last_events
        assert events_elapsed < 25, events_elapsed
        timings.append({"poll": poll, "status_s": round(status_elapsed, 3), "events_s": round(events_elapsed, 3), "state": last_status["state"], "event_count": last_events["event_count"]})

        if last_status["state"] in {"completed", "failed"}:
            break
        poll += 1
        time.sleep(5)

    evidence = {
        "endpoint": URL,
        "origin": ORIGIN,
        "tool_count": len(names),
        "tools": sorted(names),
        "initialize_seconds": round(init_elapsed, 3),
        "list_seconds": round(list_elapsed, 3),
        "analysis_start_seconds": round(start_elapsed, 3),
        "mission_id": mission_id,
        "analysis_id": analysis_id,
        "final_state": last_status.get("state"),
        "result_present": last_status.get("result") is not None,
        "events": last_events.get("events", []),
        "poll_timings": timings,
    }
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    assert last_status.get("state") in {"completed", "failed"}, evidence


if __name__ == "__main__":
    main()
