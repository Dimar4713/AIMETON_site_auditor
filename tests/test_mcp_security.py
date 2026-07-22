from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app as main_app
from app.mcp_security import McpSecurityMiddleware, SecurityConfig
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
async def test_admin_mcp_redirect_is_relative_and_proxy_safe():
    transport = ASGITransport(app=main_app)
    async with AsyncClient(
        transport=transport,
        base_url="http://internal-service",
        follow_redirects=False,
    ) as client:
        response = await client.get("/mcp-admin")

    assert response.status_code == 307
    assert response.headers["location"] == "/mcp-admin/"


@pytest.mark.asyncio
async def test_rest_health_not_redirected_by_mcp_middleware():
    transport = ASGITransport(app=main_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


class EchoApp:
    async def __call__(self, scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


async def _invoke_security(app, *, token: str | None = None):
    headers = []
    if token is not None:
        headers.append((b"authorization", f"Bearer {token}".encode("ascii")))
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": headers,
        "client": ("203.0.113.10", 12345),
    }
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    await app(scope, receive, send)
    start = next(message for message in sent if message["type"] == "http.response.start")
    body = b"".join(
        message.get("body", b"")
        for message in sent
        if message["type"] == "http.response.body"
    )
    return start["status"], dict(start.get("headers", [])), body


@pytest.mark.asyncio
async def test_public_profile_is_available_without_token():
    middleware = McpSecurityMiddleware(
        EchoApp(),
        admin=False,
        config=SecurityConfig(public_limit=2, admin_limit=1, window_seconds=60, max_concurrency=1),
    )
    status, headers, body = await _invoke_security(middleware)
    assert status == 200
    assert body == b"ok"
    assert b"x-request-id" in headers


@pytest.mark.asyncio
async def test_admin_profile_rejects_missing_and_wrong_tokens(monkeypatch):
    monkeypatch.setenv("AIMETON_MCP_ADMIN_TOKEN", "correct-token")
    middleware = McpSecurityMiddleware(EchoApp(), admin=True)
    missing_status, _, missing_body = await _invoke_security(middleware)
    wrong_status, _, _ = await _invoke_security(middleware, token="wrong-token")
    assert missing_status == 401
    assert json.loads(missing_body)["error"] == "unauthorized"
    assert wrong_status == 401


@pytest.mark.asyncio
async def test_admin_profile_accepts_correct_token(monkeypatch):
    monkeypatch.setenv("AIMETON_MCP_ADMIN_TOKEN", "correct-token")
    middleware = McpSecurityMiddleware(EchoApp(), admin=True)
    status, _, body = await _invoke_security(middleware, token="correct-token")
    assert status == 200
    assert body == b"ok"


@pytest.mark.asyncio
async def test_rate_limit_returns_429():
    middleware = McpSecurityMiddleware(
        EchoApp(),
        admin=False,
        config=SecurityConfig(public_limit=1, admin_limit=1, window_seconds=60, max_concurrency=1),
    )
    first_status, _, _ = await _invoke_security(middleware)
    second_status, _, second_body = await _invoke_security(middleware)
    assert first_status == 200
    assert second_status == 429
    assert json.loads(second_body)["error"] == "rate_limited"
