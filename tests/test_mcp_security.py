from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app as main_app
from app.mcp_server import MCP_TRANSPORT_SECURITY, _additional_allowlist_values, mcp

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
    mcp._session_manager = None
    app = mcp.streamable_http_app()
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post("/", json=INIT_PAYLOAD, headers={**BASE_HEADERS, **headers})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "host",
    [
        "auditor.aimeton.ru",
        "auditor.aimeton.ru:443",
        "stage-auditor.aimeton.ru",
        "stage-auditor.aimeton.ru:443",
        "git-hub-site-auditor.replit.app",
        "git-hub-site-auditor.replit.app:443",
    ],
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
@pytest.mark.parametrize(
    ("host", "origin"),
    [
        ("auditor.aimeton.ru", "https://auditor.aimeton.ru"),
        ("stage-auditor.aimeton.ru", "https://stage-auditor.aimeton.ru"),
        ("git-hub-site-auditor.replit.app", "https://git-hub-site-auditor.replit.app"),
    ],
)
async def test_allowed_origins_accepted(host, origin):
    resp = await _post_initialize({"Host": host, "Origin": origin})
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_arbitrary_origin_rejected():
    resp = await _post_initialize(
        {"Host": "auditor.aimeton.ru", "Origin": "https://evil.example"}
    )
    assert resp.status_code == 403
    assert "Invalid Origin" in resp.text


def test_dns_rebinding_protection_stays_enabled():
    assert MCP_TRANSPORT_SECURITY.enable_dns_rebinding_protection is True


def test_environment_allowlist_rejects_wildcards(monkeypatch):
    monkeypatch.setenv(
        "AIMETON_MCP_ALLOWED_HOSTS",
        "stage.example, *.unsafe.example, stage.example:443",
    )
    assert _additional_allowlist_values("AIMETON_MCP_ALLOWED_HOSTS") == [
        "stage.example",
        "stage.example:443",
    ]


@pytest.mark.asyncio
async def test_mcp_redirect_is_relative_and_proxy_safe():
    transport = ASGITransport(app=main_app)
    async with AsyncClient(
        transport=transport,
        base_url="http://internal-service",
        follow_redirects=False,
    ) as client:
        response = await client.get(
            "/mcp",
            headers={
                "Host": "stage-auditor.aimeton.ru",
                "X-Forwarded-Proto": "https",
            },
        )

    assert response.status_code == 307
    assert response.headers["location"] == "/mcp/"


@pytest.mark.asyncio
async def test_rest_health_not_redirected_by_mcp_middleware():
    transport = ASGITransport(app=main_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
