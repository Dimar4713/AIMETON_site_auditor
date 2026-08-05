from __future__ import annotations

import pytest

from app.mcp_server import runtime_time


@pytest.mark.asyncio
async def test_runtime_time_mcp_tool_returns_safe_fallback(monkeypatch) -> None:
    monkeypatch.delenv("AIMETON_TIME_STATUS_FILE", raising=False)
    payload = await runtime_time()
    assert payload["utc"].endswith("Z")
    assert payload["source"] == "system_clock"
    assert payload["synced"] is False
    assert payload["quality"] == "fallback"
    assert payload["reason_code"] == "canonical_status_unavailable"
    assert "path" not in payload
    assert "server" not in payload
