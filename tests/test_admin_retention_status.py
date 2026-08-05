from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.admin_workspace_api import router
from app.auth import User, UserRole
from app.auth_api import require_admin
from app.logging_pressure import LoggingMode, LoggingPressureController
from app.logging_pressure_audit import SQLiteLoggingPressureAudit
from app.logging_pressure_factory import LoggingPressureRuntime
from app.logging_pressure_runtime import LoggingPressureRuntimeOwner
from app.logging_pressure_sampler import LoggingPressureSampler
from app.retention_runner import RetentionPeriodicRunner, RetentionRunnerConfig


class _Audit:
    def __init__(self, latest):
        self._latest = latest

    def latest(self):
        return self._latest


class _Owner:
    def __init__(self, latest=None):
        self.audit = _Audit(latest)

    def run_once(self, *, protected_mission_ids=()):
        raise AssertionError("status endpoint must not run cleanup")


def _app(*, runner=None, admin=False) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    if runner is not None:
        app.state.retention_runner = runner
    if admin:
        app.dependency_overrides[require_admin] = lambda: User(
            id=1,
            username="admin",
            role=UserRole.ADMIN,
            is_active=True,
        )
    return app


def test_retention_status_requires_admin() -> None:
    response = TestClient(_app()).get("/api/admin/retention/status")
    assert response.status_code in {401, 403}


def test_retention_status_returns_safe_projection() -> None:
    latest = {
        "run_id": "retention_test",
        "started_at": "2026-08-05T00:00:00+00:00",
        "finished_at": "2026-08-05T00:00:01+00:00",
        "batches": 2,
        "deleted": 10,
        "protected": 3,
        "stopped_reason": "complete",
    }
    runner = RetentionPeriodicRunner(
        _Owner(latest),
        config=RetentionRunnerConfig(enabled=False, interval_seconds=3600),
    )
    response = TestClient(_app(runner=runner, admin=True)).get(
        "/api/admin/retention/status"
    )
    assert response.status_code == 200
    assert response.json() == {
        "enabled": False,
        "running": False,
        "interval_seconds": 3600.0,
        "latest_cleanup": latest,
        "logging_pressure": None,
    }
    encoded = response.text.lower()
    for forbidden in ("runtime-core.sqlite3", "data/", "secret", "password", "cookie"):
        assert forbidden not in encoded


def test_retention_status_includes_safe_pressure_mode(tmp_path) -> None:
    pressure_owner = LoggingPressureRuntimeOwner(
        LoggingPressureController(initial_mode=LoggingMode.MINIMAL),
        SQLiteLoggingPressureAudit(tmp_path / "runtime.sqlite3"),
    )
    pressure_runtime = LoggingPressureRuntime(
        owner=pressure_owner,
        sampler=LoggingPressureSampler(pressure_owner, lambda: None),
    )
    runner = RetentionPeriodicRunner(
        _Owner(),
        config=RetentionRunnerConfig(enabled=False),
        pressure_runtime=pressure_runtime,
    )
    response = TestClient(_app(runner=runner, admin=True)).get(
        "/api/admin/retention/status"
    )
    assert response.status_code == 200
    assert response.json()["logging_pressure"] == {
        "enabled": False,
        "running": False,
        "mode": "minimal",
        "latest_transition": None,
    }


def test_retention_status_is_503_before_lifespan_owner_exists() -> None:
    response = TestClient(_app(admin=True)).get("/api/admin/retention/status")
    assert response.status_code == 503
    assert response.json()["detail"]["reason"] == "retention_runner_unavailable"
