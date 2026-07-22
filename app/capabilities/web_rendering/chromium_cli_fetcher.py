from __future__ import annotations

import asyncio
import os
import shutil
import signal
import subprocess
import tempfile
import time

from app.scraper import FetchError, _validate_public_url, extract_visible_text
from .contract import RenderedPage

MAX_RENDERED_HTML_BYTES = 3_000_000


def _remove_profile(profile_dir: str) -> None:
    """Best-effort cleanup after Chromium has released profile files."""
    for attempt in range(5):
        try:
            shutil.rmtree(profile_dir)
            return
        except FileNotFoundError:
            return
        except OSError:
            if attempt == 4:
                shutil.rmtree(profile_dir, ignore_errors=True)
                return
            time.sleep(0.1 * (attempt + 1))


def _render(url: str, timeout_seconds: int) -> str:
    chromium = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
    if not chromium:
        raise FetchError("Системный Chromium не найден")

    profile_dir = tempfile.mkdtemp(prefix="aimeton-chromium-")
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
    process: subprocess.Popen[str] | None = None
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        # Chromium startup on shared CI runners can consume several seconds before
        # the page's virtual-time budget begins. Keep the caller's render budget,
        # but add a bounded startup/teardown allowance.
        process_timeout = max(20, timeout_seconds + 10)
        try:
            stdout, stderr = process.communicate(timeout=process_timeout)
        except subprocess.TimeoutExpired as exc:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()
            raise FetchError("Истекло время Chromium-рендеринга") from exc

        if process.returncode != 0:
            detail = stderr.strip().splitlines()[-1] if stderr.strip() else "unknown error"
            raise FetchError(f"Chromium завершился с ошибкой: {detail}")
        return stdout
    finally:
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        _remove_profile(profile_dir)


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
