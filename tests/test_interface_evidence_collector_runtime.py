from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.capabilities.interface_audit import evidence_collector as collector


class _FakeLocator:
    async def get_attribute(self, name: str):
        return "ru" if name == "lang" else None


class _FakePage:
    def __init__(self, *, dynamic: bool = False, cancel_on_goto: bool = False):
        self.dynamic = dynamic
        self.cancel_on_goto = cancel_on_goto
        self.rendered = False
        self.url = "https://fixture.test/"
        self._handlers = {}

    async def route(self, pattern, handler):
        self.route_handler = handler

    def on(self, event, handler):
        self._handlers[event] = handler

    async def goto(self, url, wait_until, timeout):
        if self.cancel_on_goto:
            raise asyncio.CancelledError()
        self.url = url

    async def wait_for_load_state(self, state, timeout):
        return None

    async def wait_for_timeout(self, milliseconds):
        self.rendered = True

    async def content(self):
        if self.dynamic and self.rendered:
            return '<html lang="ru"><body><main id="app">JS rendered</main></body></html>'
        return '<html lang="ru"><body><main>Static fixture</main></body></html>'

    async def screenshot(self, *, full_page, type):
        return b"full-page-png" if full_page else b"viewport-png"

    async def title(self):
        return "Dynamic fixture" if self.dynamic else "Static fixture"

    def locator(self, selector):
        return _FakeLocator()


class _FakeContext:
    def __init__(self, page: _FakePage):
        self.page = page
        self.closed = False

    async def new_page(self):
        return self.page

    async def close(self):
        self.closed = True


class _FakeBrowser:
    def __init__(self, context: _FakeContext):
        self.context = context
        self.closed = False

    async def new_context(self, **kwargs):
        return self.context

    async def close(self):
        self.closed = True


class _FakeChromium:
    def __init__(self, browser: _FakeBrowser):
        self.browser = browser

    async def launch(self, **kwargs):
        return self.browser


class _FakePlaywright:
    def __init__(self, browser: _FakeBrowser):
        self.chromium = _FakeChromium(browser)


class _FakePlaywrightManager:
    def __init__(self, browser: _FakeBrowser):
        self.playwright = _FakePlaywright(browser)

    async def __aenter__(self):
        return self.playwright

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _install_runtime(monkeypatch, *, dynamic: bool = False, cancel_on_goto: bool = False):
    page = _FakePage(dynamic=dynamic, cancel_on_goto=cancel_on_goto)
    context = _FakeContext(page)
    browser = _FakeBrowser(context)
    monkeypatch.setattr(collector, "_validate_public_url", lambda url: None)
    monkeypatch.setattr(collector, "async_playwright", lambda: _FakePlaywrightManager(browser))
    return page, context, browser


def test_static_fixture_produces_complete_manifest(monkeypatch, tmp_path: Path):
    _, context, browser = _install_runtime(monkeypatch)

    manifest = asyncio.run(
        collector.collect_interface_evidence(
            "https://fixture.test/static",
            tmp_path / "static",
        )
    )

    refs = {artifact.ref for artifact in manifest.artifacts}
    assert refs == {"viewport.png", "full-page.png", "dom.html", "metadata.json"}
    assert manifest.title == "Static fixture"
    assert manifest.language == "ru"
    assert all(len(artifact.sha256) == 64 for artifact in manifest.artifacts)
    assert context.closed is True
    assert browser.closed is True


def test_javascript_fixture_captures_rendered_dom(monkeypatch, tmp_path: Path):
    _, context, browser = _install_runtime(monkeypatch, dynamic=True)
    artifact_dir = tmp_path / "dynamic"

    manifest = asyncio.run(
        collector.collect_interface_evidence(
            "https://fixture.test/dynamic",
            artifact_dir,
        )
    )

    assert "JS rendered" in (artifact_dir / "dom.html").read_text(encoding="utf-8")
    assert manifest.title == "Dynamic fixture"
    assert manifest.final_url.endswith("/dynamic")
    assert context.closed is True
    assert browser.closed is True


def test_cancellation_closes_context_and_browser(monkeypatch, tmp_path: Path):
    _, context, browser = _install_runtime(monkeypatch, cancel_on_goto=True)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            collector.collect_interface_evidence(
                "https://fixture.test/cancel",
                tmp_path / "cancel",
            )
        )

    assert context.closed is True
    assert browser.closed is True
