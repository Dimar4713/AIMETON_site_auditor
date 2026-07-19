from __future__ import annotations

import asyncio
import shutil
import subprocess
import tempfile

from app.scraper import FetchError, _validate_public_url, extract_visible_text
from .contract import RenderedPage

MAX_RENDERED_HTML_BYTES = 3_000_000


def _render(url: str, timeout_seconds: int) -> str:
    chromium = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
    if not chromium:
        raise FetchError("Системный Chromium не найден")

    with tempfile.TemporaryDirectory(prefix="aimeton-chromium-") as profile_dir:
        command = [
            chromium,
            "--headless=new",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-sync",
            "--metrics-recording-only",
            "--no-first-run",
            f"--user-data-dir={profile_dir}",
            f"--virtual-time-budget={max(1000, timeout_seconds * 1000)}",
            "--dump-dom",
            url,
        ]
        try:
            completed = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout_seconds + 5,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise FetchError("Истекло время Chromium-рендеринга") from exc

        if completed.returncode != 0:
            detail = completed.stderr.strip().splitlines()[-1] if completed.stderr.strip() else "unknown error"
            raise FetchError(f"Chromium завершился с ошибкой: {detail}")
        return completed.stdout


async def fetch_rendered_site_chromium(url: str, timeout_seconds: int = 30) -> RenderedPage:
    _validate_public_url(url)
    html = await asyncio.to_thread(_render, url, timeout_seconds)
    html_size = len(html.encode("utf-8"))
    if html_size > MAX_RENDERED_HTML_BYTES:
        raise FetchError("Отрендеренная страница превышает допустимый размер")
    title, text = extract_visible_text(html)
    if len(text) < 80:
        raise FetchError("После JavaScript-рендеринга недостаточно текста")
    result = RenderedPage(
        final_url=url,
        title=title,
        text=text,
        provider="chromium-cli",
        html_bytes=html_size,
    )
    result.validate()
    return result
