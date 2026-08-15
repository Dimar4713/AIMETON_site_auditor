#!/usr/bin/env python3
from __future__ import annotations

import json
import time
from urllib.request import Request, urlopen

URL = "https://stage-auditor.aimeton.ru/mcp/"
ORIGIN = "chrome-extension://aabiopennjmopfippagcalmkdjlepdhh"
PROTOCOL_VERSION = "2025-06-18"
TARGET = "https://aimeton.ru"


def decode(body: bytes, content_type: str):
    text = body.decode("utf-8")
    if "text/event-stream" in content_type:
        lines = [line[5:].strip() for line in text.splitlines() if line.startswith("data:")]
        if not lines:
            raise RuntimeError(f"SSE response has no data: {text[:400]}")
        text = lines[-1]
    return json.loads(text) if text else None


def post(message, session_id=None):
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": PROTOCOL_VERSION,
        "Origin": ORIGIN,
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    req = Request(URL, data=json.dumps(message, separators=(",", ":")).encode(), headers=headers, method="POST")
    started = time.monotonic()
    with urlopen(req, timeout=28) as response:
        body = response.read()
        return decode(body, response.headers.get("Content-Type", "")), response.headers.get("Mcp-Session-Id") or session_id, round(time.monotonic() - started, 3)


def result(response):
    if response is None:
        return None
    if "error" in response:
        raise RuntimeError(response["error"])
    return response.get("result")


def tool_payload(tool_result):
    if not isinstance(tool_result, dict):
        raise RuntimeError(f"bad tool result: {tool_result!r}")
    structured = tool_result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    for item in tool_result.get("content", []):
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            parsed = json.loads(item["text"])
            if isinstance(parsed, dict):
                return parsed
    raise RuntimeError(f"tool returned no JSON object: {tool_result!r}")


def call(name, arguments, request_id, session_id):
    response, session_id, elapsed = post({
        "jsonrpc": "2.0", "id": request_id, "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }, session_id)
    payload = tool_payload(result(response))
    return payload, session_id, elapsed


def main():
    init, session_id, init_s = post({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {}, "clientInfo": {"name": "better-deepseek-field-acceptance", "version": "2"}},
    })
    result(init)
    post({"jsonrpc": "2.0", "method": "notifications/initialized"}, session_id)
    tools_response, session_id, list_s = post({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, session_id)
    names = sorted(tool["name"] for tool in result(tools_response).get("tools", []))
    required = {"analysis.start", "analysis.status", "analysis.events"}
    assert required.issubset(names), names

    start, session_id, start_s = call("analysis.start", {"url": TARGET}, 3, session_id)
    analysis_id = start["analysis_id"]
    mission_id = start["mission_id"]

    observations = []
    saw_progress = False
    saw_active_provider = False
    saw_heartbeat = False
    terminal = None
    request_id = 10
    deadline = time.monotonic() + 225
    poll = 1
    while time.monotonic() < deadline:
        status_payload, session_id, status_s = call("analysis.status", {"analysis_id": analysis_id, "poll": poll}, request_id, session_id)
        request_id += 1
        events_payload, session_id, events_s = call("analysis.events", {"analysis_id": analysis_id, "poll": poll}, request_id, session_id)
        request_id += 1

        progress = status_payload.get("progress") or {}
        active = progress.get("active_provider_calls") or []
        if progress.get("queries_planned", 0) or progress.get("provider_calls_finished", 0):
            saw_progress = True
        if active:
            saw_active_provider = True
        events = events_payload.get("events") or []
        if any(bool(e.get("heartbeat")) for e in events):
            saw_heartbeat = True

        row = {
            "poll": poll,
            "state": status_payload.get("state"),
            "phase": status_payload.get("phase"),
            "queries_planned": progress.get("queries_planned"),
            "queries_finished": progress.get("queries_finished"),
            "provider_calls_finished": progress.get("provider_calls_finished"),
            "provider_failures": progress.get("provider_failures"),
            "active_provider_calls": active,
            "llm_state": progress.get("llm_state"),
            "status_seconds": status_s,
            "events_seconds": events_s,
            "event_count": len(events),
        }
        observations.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

        if status_payload.get("state") in {"completed", "failed"}:
            terminal = status_payload
            break
        poll += 1
        time.sleep(7)

    evidence = {
        "endpoint": URL,
        "origin": ORIGIN,
        "deployed_target": TARGET,
        "mission_id": mission_id,
        "analysis_id": analysis_id,
        "initialize_seconds": init_s,
        "tools_list_seconds": list_s,
        "analysis_start_seconds": start_s,
        "tool_count": len(names),
        "saw_progress": saw_progress,
        "saw_active_provider": saw_active_provider,
        "saw_heartbeat": saw_heartbeat,
        "terminal_state": terminal.get("state") if terminal else None,
        "terminal_phase": terminal.get("phase") if terminal else None,
        "result_present": bool(terminal and terminal.get("result")),
        "observations": observations,
    }
    print("FINAL_EVIDENCE=" + json.dumps(evidence, ensure_ascii=False), flush=True)

    assert saw_progress, evidence
    assert terminal is not None, evidence
    assert terminal.get("state") in {"completed", "failed"}, evidence
    assert max([start_s, *[o["status_seconds"] for o in observations], *[o["events_seconds"] for o in observations]]) < 28, evidence
    if terminal.get("state") == "completed":
        assert terminal.get("result") is not None, evidence


if __name__ == "__main__":
    main()
