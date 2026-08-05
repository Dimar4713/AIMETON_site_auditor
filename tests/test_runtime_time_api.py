from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.runtime_core.api import router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_runtime_time_fallback_is_explicit(monkeypatch) -> None:
    monkeypatch.delenv("AIMETON_TIME_STATUS_FILE", raising=False)
    response = _client().get("/api/runtime/time")
    assert response.status_code == 200
    payload = response.json()
    assert payload["utc"].endswith("Z")
    assert payload["source"] == "system_clock"
    assert payload["synced"] is False
    assert payload["quality"] == "fallback"
    assert payload["reason_code"] == "canonical_status_unavailable"


def test_runtime_time_trusted_status(monkeypatch, tmp_path: Path) -> None:
    status = tmp_path / "time-status.json"
    status.write_text(
        json.dumps({"source": "chrony", "synced": True, "offset_ms": 1.25, "stratum": 2}),
        encoding="utf-8",
    )
    monkeypatch.setenv("AIMETON_TIME_STATUS_FILE", str(status))
    monkeypatch.setenv("AIMETON_TIME_MAX_OFFSET_MS", "50")
    monkeypatch.setenv("AIMETON_TIME_MAX_STRATUM", "4")

    response = _client().get("/api/runtime/time")
    assert response.status_code == 200
    payload = response.json()
    assert payload["synced"] is True
    assert payload["quality"] == "trusted"
    assert payload["offset_ms"] == 1.25
    assert payload["stratum"] == 2
    assert payload["reason_code"] is None


def test_runtime_time_degraded_when_policy_fails(monkeypatch, tmp_path: Path) -> None:
    status = tmp_path / "time-status.json"
    status.write_text(
        json.dumps({"source": "chrony", "synced": True, "offset_ms": 120.0, "stratum": 5}),
        encoding="utf-8",
    )
    monkeypatch.setenv("AIMETON_TIME_STATUS_FILE", str(status))
    monkeypatch.setenv("AIMETON_TIME_MAX_OFFSET_MS", "50")
    monkeypatch.setenv("AIMETON_TIME_MAX_STRATUM", "4")

    payload = _client().get("/api/runtime/time").json()
    assert payload["quality"] == "degraded"
    assert payload["reason_code"] == "time_policy_not_satisfied"


def test_runtime_time_health_fails_closed_by_default(monkeypatch) -> None:
    monkeypatch.delenv("AIMETON_TIME_STATUS_FILE", raising=False)
    monkeypatch.delenv("AIMETON_TIME_REQUIRE_SYNC", raising=False)
    payload = _client().get("/api/runtime/time/health").json()
    assert payload["status"] == "failed"
    assert payload["quality"] == "fallback"


def test_runtime_time_response_does_not_expose_status_path(monkeypatch, tmp_path: Path) -> None:
    status = tmp_path / "private-time-status.json"
    status.write_text("not-json", encoding="utf-8")
    monkeypatch.setenv("AIMETON_TIME_STATUS_FILE", str(status))
    response = _client().get("/api/runtime/time")
    assert response.status_code == 200
    assert str(status) not in response.text
    assert "private-time-status" not in response.text
    assert response.json()["reason_code"] == "canonical_status_invalid"
