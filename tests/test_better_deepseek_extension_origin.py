from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.mcp_security import (
    BETTER_DEEPSEEK_CHROME_EXTENSION_ORIGIN,
    McpSecurityMiddleware,
    browser_mcp_origins,
)
from app.mcp_server import mcp

INIT_PAYLOAD = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "better-deepseek", "version": "0.1.12"},
    },
}

BASE_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


async def _post_initialize(origin: str):
    mcp._session_manager = None
    app = mcp.streamable_http_app()
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post(
                "/",
                json=INIT_PAYLOAD,
                headers={
                    **BASE_HEADERS,
                    "Host": "stage-auditor.aimeton.ru",
                    "Origin": origin,
                },
            )


@pytest.mark.asyncio
async def test_official_better_deepseek_chrome_extension_origin_reaches_fastmcp():
    response = await _post_initialize(BETTER_DEEPSEEK_CHROME_EXTENSION_ORIGIN)
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_unknown_chrome_extension_origin_is_rejected_by_fastmcp():
    response = await _post_initialize(
        "chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    )
    assert response.status_code == 403
    assert "Invalid Origin" in response.text


def test_official_extension_origin_is_explicit_not_wildcard():
    origins = browser_mcp_origins()
    assert BETTER_DEEPSEEK_CHROME_EXTENSION_ORIGIN in origins
    assert all("*" not in origin for origin in origins)


class EchoApp:
    async def __call__(self, scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


async def _invoke_preflight(origin: str):
    middleware = McpSecurityMiddleware(EchoApp(), admin=False)
    scope = {
        "type": "http",
        "method": "OPTIONS",
        "path": "/",
        "headers": [
            (b"origin", origin.encode("ascii")),
            (b"access-control-request-method", b"POST"),
            (
                b"access-control-request-headers",
                b"content-type,x-api-key,mcp-session-id",
            ),
        ],
        "client": ("203.0.113.10", 12345),
    }
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    await middleware(scope, receive, send)
    start = next(message for message in sent if message["type"] == "http.response.start")
    body = b"".join(
        message.get("body", b"")
        for message in sent
        if message["type"] == "http.response.body"
    )
    return start["status"], dict(start.get("headers", [])), body


@pytest.mark.asyncio
async def test_official_extension_origin_gets_public_mcp_preflight():
    status, headers, body = await _invoke_preflight(
        BETTER_DEEPSEEK_CHROME_EXTENSION_ORIGIN
    )
    assert status == 204
    assert body == b""
    assert headers[b"access-control-allow-origin"] == (
        BETTER_DEEPSEEK_CHROME_EXTENSION_ORIGIN.encode("ascii")
    )
    assert b"x-api-key" in headers[b"access-control-allow-headers"].lower()


@pytest.mark.asyncio
async def test_unknown_extension_origin_preflight_is_rejected():
    status, headers, body = await _invoke_preflight(
        "chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    )
    assert status == 403
    assert b"access-control-allow-origin" not in headers
    assert json.loads(body)["error"] == "cors_origin_rejected"
