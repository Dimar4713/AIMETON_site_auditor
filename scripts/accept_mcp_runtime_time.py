#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


def _tool_payload(result: Any) -> dict[str, Any]:
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured

    for item in getattr(result, "content", []):
        text = getattr(item, "text", None)
        if isinstance(text, str):
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
    raise AssertionError("runtime.time returned no JSON object")


async def accept(url: str) -> dict[str, Any]:
    async with streamablehttp_client(url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            assert "runtime.time" in names, sorted(names)
            result = await session.call_tool("runtime.time", {})

    assert not result.isError, result
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
    evidence = asyncio.run(accept(args.url))
    rendered = json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2)
    print(rendered)
    if args.evidence:
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
