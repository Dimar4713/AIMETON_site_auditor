from __future__ import annotations

import contextlib
import socket
import subprocess
import time
from pathlib import Path

import pytest

from app.capabilities.web_rendering.chromium_cli_fetcher import fetch_rendered_site_chromium
from app.capabilities.web_rendering.playwright_fetcher import fetch_rendered_site
from app.capabilities.web_rendering.resolver import needs_dynamic_rendering
from app.scraper import extract_visible_text, FetchError


@contextlib.contextmanager
def local_http_server(directory: Path):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    proc = subprocess.Popen(
        ["python", "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(directory)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(0.3)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_dynamic_detection_on_static_html():
    html = Path("tests/fixtures/dynamic.html").read_text(encoding="utf-8")
    _, text = extract_visible_text(html)
    assert needs_dynamic_rendering(html, text)
    assert "Облачная платформа" not in text


@pytest.mark.asyncio
async def test_chromium_cli_contract_with_local_fixture(monkeypatch):
    monkeypatch.setattr("app.capabilities.web_rendering.chromium_cli_fetcher._validate_public_url", lambda _: None)
    fixture_dir = Path("tests/fixtures").resolve()
    with local_http_server(fixture_dir) as base:
        try:
            result = await fetch_rendered_site_chromium(f"{base}/dynamic.html", timeout_seconds=5)
        except FetchError as exc:
            pytest.xfail(f"Sandbox browser runtime unavailable: {exc}")
    assert result.provider == "chromium-cli"
    assert result.title == "AIMETON Engineering Cloud"
    assert "Облачная платформа для инженерных команд" in result.text
    assert "управляемые базы данных" in result.text
    assert result.html_bytes > 0


@pytest.mark.asyncio
async def test_playwright_candidate_failure_is_controlled(monkeypatch):
    monkeypatch.setattr("app.capabilities.web_rendering.playwright_fetcher._validate_public_url", lambda _: None)
    fixture_dir = Path("tests/fixtures").resolve()
    with local_http_server(fixture_dir) as base:
        try:
            result = await fetch_rendered_site(f"{base}/dynamic.html", timeout_seconds=5)
            assert result.provider == "playwright"
        except FetchError as exc:
            assert "рендеринга" in str(exc).lower()


@pytest.mark.asyncio
async def test_private_network_blocked():
    with pytest.raises(FetchError):
        await fetch_rendered_site_chromium("http://127.0.0.1:9999")
