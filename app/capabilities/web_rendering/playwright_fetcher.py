from __future__ import annotations

import asyncio
from urllib.parse import urlparse

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

from app.scraper import FetchError, _validate_public_url, extract_visible_text
from .contract import RenderedPage

MAX_RENDERED_HTML_BYTES = 3_000_000


async def fetch_rendered_site(url: str, timeout_seconds: int = 30) -> RenderedPage:
    _validate_public_url(url)
    timeout_ms = timeout_seconds * 1000
    browser = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                executable_path="/usr/bin/chromium",
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = await browser.new_context(
                user_agent="AIMETON-Site-Auditor/0.2 Playwright",
                java_script_enabled=True,
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

            await page.route("**/*", guard_route)
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                await page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 8000))
            except PlaywrightTimeoutError:
                pass
            await page.wait_for_timeout(500)
            html = await page.content()
            html_size = len(html.encode("utf-8"))
            if html_size > MAX_RENDERED_HTML_BYTES:
                raise FetchError("Отрендеренная страница превышает допустимый размер")
            title, text = extract_visible_text(html)
            if len(text) < 80:
                raise FetchError("После JavaScript-рендеринга недостаточно текста")
            result = RenderedPage(
                final_url=page.url,
                title=title,
                text=text,
                provider="playwright",
                html_bytes=html_size,
            )
            result.validate()
            await context.close()
            await browser.close()
            browser = None
            return result
    except PlaywrightTimeoutError as exc:
        raise FetchError("Истекло время JavaScript-рендеринга") from exc
    except asyncio.CancelledError:
        raise
    except FetchError:
        raise
    except Exception as exc:
        raise FetchError(f"Ошибка JavaScript-рендеринга: {exc}") from exc
    finally:
        if browser is not None:
            await browser.close()
