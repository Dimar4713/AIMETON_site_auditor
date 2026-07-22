from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Awaitable, Callable
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

LOGGER = logging.getLogger("aimeton.mcp.security")


@dataclass(frozen=True)
class SecurityConfig:
    public_limit: int = 30
    admin_limit: int = 20
    window_seconds: int = 60
    max_concurrency: int = 4

    @classmethod
    def from_env(cls) -> "SecurityConfig":
        return cls(
            public_limit=max(1, int(os.getenv("AIMETON_MCP_PUBLIC_RATE_LIMIT", "30"))),
            admin_limit=max(1, int(os.getenv("AIMETON_MCP_ADMIN_RATE_LIMIT", "20"))),
            window_seconds=max(1, int(os.getenv("AIMETON_MCP_RATE_WINDOW_SECONDS", "60"))),
            max_concurrency=max(1, int(os.getenv("AIMETON_MCP_MAX_CONCURRENCY", "4"))),
        )


class SlidingWindowLimiter:
    def __init__(self, window_seconds: int) -> None:
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def allow(self, key: str, limit: int) -> bool:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        async with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                return False
            events.append(now)
            return True


def _json_response(status: int, payload: dict) -> tuple[int, list[tuple[bytes, bytes]], bytes]:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = [
        (b"content-type", b"application/json; charset=utf-8"),
        (b"content-length", str(len(body)).encode("ascii")),
        (b"cache-control", b"no-store"),
    ]
    return status, headers, body


async def _send_json(send: Send, status: int, payload: dict) -> None:
    status, headers, body = _json_response(status, payload)
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


def _header(scope: Scope, name: bytes) -> str:
    for key, value in scope.get("headers", []):
        if key.lower() == name:
            return value.decode("latin-1")
    return ""


def _safe_actor(scope: Scope, token: str | None) -> str:
    if token:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]
        return f"token:{digest}"
    client = scope.get("client")
    host = client[0] if client else "unknown"
    digest = hashlib.sha256(host.encode("utf-8")).hexdigest()[:12]
    return f"anonymous:{digest}"


class McpSecurityMiddleware:
    """Protect MCP endpoints without logging tokens or request contents."""

    def __init__(self, app: ASGIApp, *, admin: bool, config: SecurityConfig | None = None) -> None:
        self.app = app
        self.admin = admin
        self.config = config or SecurityConfig.from_env()
        self.limiter = SlidingWindowLimiter(self.config.window_seconds)
        self.semaphore = asyncio.Semaphore(self.config.max_concurrency)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _header(scope, b"x-request-id") or str(uuid4())
        authorization = _header(scope, b"authorization")
        token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else None
        actor = _safe_actor(scope, token)
        profile = "admin" if self.admin else "public"
        started = time.perf_counter()

        if self.admin:
            expected = os.getenv("AIMETON_MCP_ADMIN_TOKEN", "")
            if not expected or token is None or not hmac.compare_digest(token, expected):
                self._audit(actor, profile, request_id, "unauthorized", started)
                await _send_json(
                    send,
                    401,
                    {"error": "unauthorized", "request_id": request_id},
                )
                return

        limit = self.config.admin_limit if self.admin else self.config.public_limit
        if not await self.limiter.allow(f"{profile}:{actor}", limit):
            self._audit(actor, profile, request_id, "rate_limited", started)
            await _send_json(
                send,
                429,
                {"error": "rate_limited", "request_id": request_id},
            )
            return

        acquired = False
        try:
            await asyncio.wait_for(self.semaphore.acquire(), timeout=0.05)
            acquired = True
        except TimeoutError:
            self._audit(actor, profile, request_id, "concurrency_limited", started)
            await _send_json(
                send,
                503,
                {"error": "concurrency_limited", "request_id": request_id},
            )
            return

        status_code = 500

        async def audited_send(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, audited_send)
        finally:
            if acquired:
                self.semaphore.release()
            result = "success" if status_code < 400 else f"http_{status_code}"
            self._audit(actor, profile, request_id, result, started)

    @staticmethod
    def _audit(actor: str, profile: str, request_id: str, result: str, started: float) -> None:
        LOGGER.info(
            "mcp_security actor=%s profile=%s request_id=%s result=%s duration_ms=%d timestamp=%d",
            actor,
            profile,
            request_id,
            result,
            int((time.perf_counter() - started) * 1000),
            int(time.time()),
        )
