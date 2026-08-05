from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

import app.main as main


class _FakeRunner:
    def __init__(self) -> None:
        self.started = 0
        self.stopped = 0

    async def start(self) -> None:
        self.started += 1

    async def stop(self) -> None:
        self.stopped += 1


@asynccontextmanager
async def _session():
    yield


@pytest.mark.asyncio
async def test_lifespan_owns_single_retention_runner(monkeypatch, tmp_path):
    runner = _FakeRunner()
    monkeypatch.setenv("AIMETON_RUNTIME_DB", str(tmp_path / "runtime.sqlite3"))
    monkeypatch.setattr(main, "build_retention_runner", lambda path: runner)
    monkeypatch.setattr(main.mcp.session_manager, "run", _session)
    monkeypatch.setattr(main.admin_mcp.session_manager, "run", _session)

    async with main.lifespan(main.app):
        assert main.app.state.retention_runner is runner
        assert runner.started == 1
        assert runner.stopped == 0

    assert runner.stopped == 1


@pytest.mark.asyncio
async def test_lifespan_stops_retention_runner_when_session_fails(monkeypatch, tmp_path):
    runner = _FakeRunner()
    monkeypatch.setenv("AIMETON_RUNTIME_DB", str(tmp_path / "runtime.sqlite3"))
    monkeypatch.setattr(main, "build_retention_runner", lambda path: runner)

    @asynccontextmanager
    async def failing_session():
        raise RuntimeError("session start failed")
        yield

    monkeypatch.setattr(main.mcp.session_manager, "run", failing_session)
    monkeypatch.setattr(main.admin_mcp.session_manager, "run", _session)

    with pytest.raises(RuntimeError, match="session start failed"):
        async with main.lifespan(main.app):
            pass

    assert runner.started == 1
    assert runner.stopped == 1
