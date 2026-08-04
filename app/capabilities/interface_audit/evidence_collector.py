from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import TimeoutError as PlaywrightTimeoutError, async_playwright

from app.capabilities.web_rendering.playwright_fetcher import MAX_RENDERED_HTML_BYTES
from app.scraper import FetchError, _validate_public_url
from .evidence_contract import EvidenceArtifact, InterfaceEvidenceManifest
from .rule_pack import load_rule_pack

MAX_SCREENSHOT_BYTES = 8_000_000
MAX_EVENT_ITEMS = 200
_SECRET_PATTERN = re.compile(
    r"(?i)(authorization|cookie|set-cookie|api[_-]?key|token|secret|password)\s*[:=]\s*([^\s,;]+)"
)
_PATH_PATTERN = re.compile(r"(?:/home/runner|/opt/aimeton|/app/)[^\s\"']+")


def _sanitize_text(value: str, limit: int = 2_000) -> str:
    value = _SECRET_PATTERN.sub(r"\1=[REDACTED]", value)
    value = _PATH_PATTERN.sub("[INTERNAL_PATH]", value)
    return value[:limit]


def _artifact(ref: str, content_type: str, payload: bytes) -> EvidenceArtifact:
    return EvidenceArtifact.from_bytes(ref=ref, content_type=content_type, payload=payload)


async def collect_interface_evidence(
    url: str,
    artifact_dir: Path,
    *,
    timeout_seconds: int = 30,
    viewport_width: int = 1440,
    viewport_height: int = 900,
    color_scheme: str = "light",
    reduced_motion: str = "reduce",
) -> InterfaceEvidenceManifest:
    """Collect read-only browser evidence using the existing Playwright runtime and SSRF policy."""

    _validate_public_url(url)
    if timeout_seconds <= 0 or timeout_seconds > 120:
        raise ValueError("timeout_seconds must be between 1 and 120")
    if color_scheme not in {"light", "dark", "no-preference"}:
        raise ValueError("unsupported color_scheme")
    if reduced_motion not in {"reduce", "no-preference"}:
        raise ValueError("unsupported reduced_motion")

    artifact_dir.mkdir(parents=True, exist_ok=True)
    timeout_ms = timeout_seconds * 1000
    console_messages: list[dict[str, str]] = []
    page_errors: list[str] = []
    failed_requests: list[dict[str, str]] = []
    redirects: list[dict[str, str]] = []
    browser = None
    context = None

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                executable_path="/usr/bin/chromium",
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = await browser.new_context(
                user_agent="AIMETON-Interface-Audit/0.1 Playwright",
                java_script_enabled=True,
                viewport={"width": viewport_width, "height": viewport_height},
                color_scheme=color_scheme,
                reduced_motion=reduced_motion,
            )
            page = await context.new_page()

            async def guard_route(route):
                request_url = route.request.url
                parsed = urlparse(request_url)
                if parsed.scheme not in {"http", "https", "data", "blob"}:
                    await route.abort()
                    return
                if parsed.scheme in {"http", "https"}:
                    try:
                        _validate_public_url(request_url)
                    except FetchError:
                        await route.abort()
                        return
                await route.continue_()

            def on_console(message):
                if len(console_messages) < MAX_EVENT_ITEMS:
                    console_messages.append({"type": message.type, "text": _sanitize_text(message.text)})

            def on_page_error(error):
                if len(page_errors) < MAX_EVENT_ITEMS:
                    page_errors.append(_sanitize_text(str(error)))

            def on_request_failed(request):
                if len(failed_requests) < MAX_EVENT_ITEMS:
                    failed_requests.append(
                        {
                            "url": _sanitize_text(request.url),
                            "method": request.method,
                            "failure": _sanitize_text(request.failure or "unknown"),
                        }
                    )

            def on_response(response):
                request = response.request
                redirected_from = request.redirected_from
                if redirected_from is not None and len(redirects) < MAX_EVENT_ITEMS:
                    redirects.append(
                        {
                            "from": _sanitize_text(redirected_from.url),
                            "to": _sanitize_text(request.url),
                            "status": str(response.status),
                        }
                    )

            await page.route("**/*", guard_route)
            page.on("console", on_console)
            page.on("pageerror", on_page_error)
            page.on("requestfailed", on_request_failed)
            page.on("response", on_response)

            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                await page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 8_000))
            except PlaywrightTimeoutError:
                pass
            await page.wait_for_timeout(500)

            html = await page.content()
            html_payload = html.encode("utf-8")
            if len(html_payload) > MAX_RENDERED_HTML_BYTES:
                raise FetchError("DOM snapshot exceeds the allowed size")

            viewport_png = await page.screenshot(full_page=False, type="png")
            full_page_png = await page.screenshot(full_page=True, type="png")
            if len(viewport_png) > MAX_SCREENSHOT_BYTES or len(full_page_png) > MAX_SCREENSHOT_BYTES:
                raise FetchError("Screenshot exceeds the allowed size")

            metadata = {
                "final_url": page.url,
                "title": await page.title(),
                "language": await page.locator("html").get_attribute("lang"),
                "viewport": {"width": viewport_width, "height": viewport_height},
                "color_scheme": color_scheme,
                "reduced_motion": reduced_motion,
            }
            metadata_payload = json.dumps(metadata, ensure_ascii=False, sort_keys=True).encode("utf-8")

            payloads = {
                "viewport.png": viewport_png,
                "full-page.png": full_page_png,
                "dom.html": html_payload,
                "metadata.json": metadata_payload,
            }
            for name, payload in payloads.items():
                (artifact_dir / name).write_bytes(payload)

            rule_pack = load_rule_pack()
            manifest = InterfaceEvidenceManifest(
                final_url=page.url,
                title=metadata["title"],
                language=metadata["language"],
                viewport=metadata["viewport"],
                color_scheme=color_scheme,
                reduced_motion=reduced_motion,
                rule_pack_version=rule_pack.version,
                rule_pack_digest=rule_pack.digest,
                artifacts=(
                    _artifact("viewport.png", "image/png", viewport_png),
                    _artifact("full-page.png", "image/png", full_page_png),
                    _artifact("dom.html", "text/html; charset=utf-8", html_payload),
                    _artifact("metadata.json", "application/json", metadata_payload),
                ),
                console_messages=tuple(console_messages),
                page_errors=tuple(page_errors),
                failed_requests=tuple(failed_requests),
                redirects=tuple(redirects),
            )
            manifest.validate()
            return manifest
    except PlaywrightTimeoutError as exc:
        raise FetchError("Interface evidence collection timed out") from exc
    except asyncio.CancelledError:
        raise
    except FetchError:
        raise
    except Exception as exc:
        raise FetchError(f"Interface evidence collection failed: {exc}") from exc
    finally:
        if context is not None:
            await context.close()
        if browser is not None:
            await browser.close()
