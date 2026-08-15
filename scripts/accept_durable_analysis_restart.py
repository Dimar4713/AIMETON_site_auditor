#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

URL = "https://stage-auditor.aimeton.ru/mcp/"
ORIGIN = "chrome-extension://aabiopennjmopfippagcalmkdjlepdhh"
PROTOCOL_VERSION = "2025-06-18"
TARGET = "https://aimeton.ru"
REQUEST_TIMEOUT = 25
WAIT_LLM_SECONDS = 100
POLL_SECONDS = 3


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
    try:
        with urlopen(req, timeout=REQUEST_TIMEOUT) as response:
            elapsed = time.monotonic() - started
            assert response.headers.get("Access-Control-Allow-Origin") == ORIGIN, dict(response.headers)
            sid = response.headers.get("Mcp-Session-Id") or session_id
            body = response.read()
            return (decode(body, response.headers.get("Content-Type", "")) if body else None), sid, elapsed
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise AssertionError(f"MCP HTTP {exc.code}: {body[:1000]}") from exc


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


def initialize() -> tuple[str | None, set[str]]:
    init, session_id, _ = post(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "aimeton-durable-restart-acceptance", "version": "1"},
            },
        }
    )
    rpc_result(init)
    post({"jsonrpc": "2.0", "method": "notifications/initialized"}, session_id)
    listed, _, _ = post(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, session_id
    )
    names = {item["name"] for item in rpc_result(listed).get("tools", [])}
    return session_id, names


def call(
    session_id: str | None,
    request_id: int,
    tool: str,
    args: dict[str, Any],
) -> tuple[dict[str, Any], float]:
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


def append_github_output(values: dict[str, Any]) -> None:
    output = os.getenv("GITHUB_OUTPUT")
    if not output:
        return
    with Path(output).open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def start_mode(expected_sha: str) -> None:
    session_id, names = initialize()
    assert {
        "runtime.convergence",
        "analysis.start",
        "analysis.status",
        "analysis.events",
    } <= names, sorted(names)

    request_id = 3
    convergence, _ = call(session_id, request_id, "runtime.convergence", {})
    request_id += 1
    assert convergence.get("state") == "converged", convergence
    assert convergence.get("deployment_sha") == expected_sha, convergence
    assert convergence.get("marker_deployment_sha") == expected_sha, convergence
    assert convergence.get("marker_error") is None, convergence
    old_runtime_instance = convergence.get("runtime_instance_id")
    assert isinstance(old_runtime_instance, str) and len(old_runtime_instance) == 32, convergence

    started, start_seconds = call(session_id, request_id, "analysis.start", {"url": TARGET})
    request_id += 1
    analysis_id = started["analysis_id"]
    mission_id = started["mission_id"]
    poll = int(started["next_poll"])
    deadline = time.monotonic() + WAIT_LLM_SECONDS
    snapshots: list[dict[str, Any]] = []

    while time.monotonic() < deadline:
        status, status_seconds = call(
            session_id,
            request_id,
            "analysis.status",
            {"analysis_id": analysis_id, "poll": poll},
        )
        request_id += 1
        progress = status.get("progress") or {}
        snapshots.append(
            {
                "poll": poll,
                "state": status.get("state"),
                "phase": status.get("phase"),
                "queries_planned": progress.get("queries_planned"),
                "queries_finished": progress.get("queries_finished"),
                "llm_state": progress.get("llm_state"),
                "llm_elapsed_seconds": progress.get("llm_elapsed_seconds"),
                "status_seconds": round(status_seconds, 3),
            }
        )
        if status.get("state") in {"completed", "failed"}:
            raise AssertionError({"reason": "analysis_finished_before_restart_window", "snapshots": snapshots})
        if progress.get("llm_state") == "running" or status.get("phase") == "llm_synthesis_running":
            evidence = {
                "expected_sha": expected_sha,
                "old_runtime_instance": old_runtime_instance,
                "mission_id": mission_id,
                "analysis_id": analysis_id,
                "next_poll": poll + 1,
                "analysis_start_seconds": round(start_seconds, 3),
                "pre_restart_status": status,
                "snapshots": snapshots,
            }
            print(json.dumps(evidence, ensure_ascii=False, indent=2))
            append_github_output(
                {
                    "analysis_id": analysis_id,
                    "mission_id": mission_id,
                    "next_poll": poll + 1,
                    "old_runtime_instance": old_runtime_instance,
                }
            )
            return
        poll += 1
        time.sleep(POLL_SECONDS)

    raise AssertionError({"reason": "llm_phase_not_reached", "snapshots": snapshots})


def verify_mode(
    expected_sha: str,
    analysis_id: str,
    mission_id: str,
    poll: int,
    old_runtime_instance: str,
) -> None:
    session_id, names = initialize()
    assert {"runtime.convergence", "analysis.status", "analysis.events"} <= names, sorted(names)
    request_id = 3

    convergence, convergence_seconds = call(session_id, request_id, "runtime.convergence", {})
    request_id += 1
    assert convergence.get("state") == "stale", convergence
    assert convergence.get("marker_error") == "runtime_instance_mismatch", convergence
    assert convergence.get("deployment_sha") == expected_sha, convergence
    assert convergence.get("marker_deployment_sha") == expected_sha, convergence
    assert convergence.get("marker_runtime_instance_id") == old_runtime_instance, convergence
    new_runtime_instance = convergence.get("runtime_instance_id")
    assert isinstance(new_runtime_instance, str) and len(new_runtime_instance) == 32, convergence
    assert new_runtime_instance != old_runtime_instance, convergence

    status, status_seconds = call(
        session_id,
        request_id,
        "analysis.status",
        {"analysis_id": analysis_id, "poll": poll},
    )
    request_id += 1
    events, events_seconds = call(
        session_id,
        request_id,
        "analysis.events",
        {"analysis_id": analysis_id, "poll": poll},
    )

    assert status.get("analysis_id") == analysis_id, status
    assert status.get("mission_id") == mission_id, status
    assert status.get("state") == "stalled", status
    assert status.get("phase") == "runtime_restart_detected", status
    assert status.get("interrupted_by_runtime_restart") is True, status
    assert status.get("interruption_reason") == "runtime_instance_changed", status
    assert status.get("resume_required") is True, status
    assert status.get("resume_supported") is False, status
    assert status.get("result") is None, status
    progress = status.get("progress") or {}
    assert progress.get("active_provider_calls") == [], progress
    assert progress.get("llm_state") != "running", progress

    event_list = events.get("events") or []
    assert event_list, events
    assert any(event.get("event_code") == "mission.received" for event in event_list), events
    assert event_list[-1].get("phase") == "runtime_restart_detected", events
    assert event_list[-1].get("event_code") == "flow.gap_detected", events
    assert event_list[-1].get("state") == "stalled", events

    evidence = {
        "expected_sha": expected_sha,
        "analysis_id": analysis_id,
        "mission_id": mission_id,
        "old_runtime_instance": old_runtime_instance,
        "new_runtime_instance": new_runtime_instance,
        "convergence_seconds": round(convergence_seconds, 3),
        "status_seconds": round(status_seconds, 3),
        "events_seconds": round(events_seconds, 3),
        "post_restart_status": status,
        "event_count": len(event_list),
        "last_event": event_list[-1],
    }
    print(json.dumps(evidence, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)

    start = sub.add_parser("start")
    start.add_argument("--expected-sha", required=True)

    verify = sub.add_parser("verify")
    verify.add_argument("--expected-sha", required=True)
    verify.add_argument("--analysis-id", required=True)
    verify.add_argument("--mission-id", required=True)
    verify.add_argument("--poll", required=True, type=int)
    verify.add_argument("--old-runtime-instance", required=True)

    args = parser.parse_args()
    if args.mode == "start":
        start_mode(args.expected_sha)
    else:
        verify_mode(
            args.expected_sha,
            args.analysis_id,
            args.mission_id,
            args.poll,
            args.old_runtime_instance,
        )


if __name__ == "__main__":
    main()
