from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.mcp_server import mcp

INIT_PAYLOAD = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "pytest", "version": "0"},
    },
}

BASE_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


async def _post_initialize(headers: dict[str, str]):
    # Свежий session manager на каждый тест: .run() допускается один раз на инстанс.
    mcp._session_manager = None
    app = mcp.streamable_http_app()
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post("/", json=INIT_PAYLOAD, headers={**BASE_HEADERS, **headers})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "host",
    ["auditor.aimeton.ru", "auditor.aimeton.ru:443", "git-hub-site-auditor.replit.app"],
)
async def test_allowed_hosts_accepted(host):
    resp = await _post_initialize({"Host": host})
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_evil_host_rejected():
    resp = await _post_initialize({"Host": "evil.example"})
    assert resp.status_code == 421
    assert "Invalid Host" in resp.text


@pytest.mark.asyncio
async def test_allowed_origin_accepted():
    resp = await _post_initialize(
        {"Host": "auditor.aimeton.ru", "Origin": "https://auditor.aimeton.ru"}
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_arbitrary_origin_rejected():
    resp = await _post_initialize(
        {"Host": "auditor.aimeton.ru", "Origin": "https://evil.example"}
    )
    assert resp.status_code == 403
    assert "Invalid Origin" in resp.text
