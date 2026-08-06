#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

PROTOCOL_VERSION = "2025-06-18"


def _decode_response(body: bytes, content_type: str) -> dict[str, Any]:
    text = body.decode("utf-8")
    if "text/event-stream" in content_type:
        data_lines = [line[5:].strip() for line in text.splitlines() if line.startswith("data:")]
        if not data_lines:
            raise AssertionError(f"MCP SSE response contained no data event: {text!r}")
        text = data_lines[-1]
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise AssertionError("MCP response is not a JSON object")
    return payload


def _post(url: str, message: dict[str, Any], session_id: str | None = None) -> tuple[dict[str, Any] | None, str | None]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": PROTOCOL_VERSION,
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    request = Request(
        url,
        data=json.dumps(message, separators=(",", ":")).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        new_session = response.headers.get("Mcp-Session-Id") or session_id
        body = response.read()
        if not body:
            return None, new_session
        return _decode_response(body, response.headers.get("Content-Type", "")), new_session


def _result(response: dict[str, Any] | None) -> Any:
    assert response is not None, "MCP request returned an empty response"
    assert "error" not in response, response
    assert "result" in response, response
    return response["result"]


def _tool_payload(result: dict[str, Any]) -> dict[str, Any]:
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    for item in result.get("content", []):
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            parsed = json.loads(item["text"])
            if isinstance(parsed, dict):
                return parsed
    raise AssertionError("runtime.time returned no JSON object")


def accept(url: str) -> dict[str, Any]:
    initialize, session_id = _post(
        url,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "aimeton-runtime-time-acceptance", "version": "1"},
            },
        },
    )
    _result(initialize)
    assert session_id, "MCP server did not return Mcp-Session-Id"

    _post(url, {"jsonrpc": "2.0", "method": "notifications/initialized"}, session_id)
    tools_response, _ = _post(url, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, session_id)
    tools = _result(tools_response)
    names = {item["name"] for item in tools.get("tools", [])}
    assert "runtime.time" in names, sorted(names)

    call_response, _ = _post(
        url,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "runtime.time", "arguments": {}},
        },
        session_id,
    )
    result = _result(call_response)
    assert result.get("isError") is not True, result
    payload = _tool_payload(result)
    assert payload["source"] == "chrony", payload
    assert payload["synced"] is True, payload
    assert payload["quality"] == "trusted", payload
    assert abs(float(payload["offset_ms"])) <= 50, payload
    assert int(payload["stratum"]) <= 4, payload
    assert isinstance(payload["utc"], str) and payload["utc"].endswith("Z"), payload
    return {
        "transport": "mcp-streamable-http",
        "tool": "runtime.time",
        "endpoint": url,
        "result": payload,
        "secret_values_exposed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="https://stage-auditor.aimeton.ru/mcp/")
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    evidence = accept(args.url)
    rendered = json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2)
    print(rendered)
    if args.evidence:
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
