from __future__ import annotations

from app.scraper import FetchError, fetch_site
from .chromium_cli_fetcher import fetch_rendered_site_chromium
from .contract import RenderedPage
from .playwright_fetcher import fetch_rendered_site as fetch_rendered_site_playwright

MIN_STATIC_TEXT = 500
JS_MARKERS = (
    "__next_data__",
    'id="root"',
    "id='root'",
    "enable javascript",
    "javascript is required",
)


def needs_dynamic_rendering(html_or_text: str, extracted_text: str) -> bool:
    source = html_or_text.lower()
    return len(extracted_text.strip()) < MIN_STATIC_TEXT or any(marker in source for marker in JS_MARKERS)


async def fetch_with_capability_resolution(url: str) -> RenderedPage:
    try:
        static = await fetch_site(url, allow_insufficient=True)
        if not needs_dynamic_rendering(static.get("html", ""), static["text"]):
            result = RenderedPage(
                final_url=static["final_url"],
                title=static["title"],
                text=static["text"],
                provider="httpx",
                html_bytes=len(static.get("html", "").encode("utf-8")),
            )
            result.validate()
            return result
    except FetchError:
        pass

    try:
        return await fetch_rendered_site_playwright(url)
    except FetchError:
        return await fetch_rendered_site_chromium(url)
