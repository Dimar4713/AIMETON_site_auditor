from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.runtime_core.api import router
from app.umel import REGISTRY, UMEL_VERSION


def test_umel_codes_are_unique_and_icons_are_stable() -> None:
    assert len(REGISTRY) == 25
    assert REGISTRY["mission.received"].icon == "🧭"
    assert REGISTRY["critical_path.active"].icon == "🔥"
    assert REGISTRY["flow.gap_detected"].icon == "🚧"
    assert REGISTRY["owner.decision_required"].icon == "👤"
    assert REGISTRY["mission.completed"].icon == "🎉"
    assert REGISTRY["mission.completed"].terminal is True
    assert REGISTRY["mission.failed"].terminal is True
    assert REGISTRY["stage.completed"].terminal is False


def test_umel_runtime_endpoint_returns_versioned_safe_registry() -> None:
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).get("/api/runtime/umel")
    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == UMEL_VERSION
    assert len(payload["events"]) == len(REGISTRY)
    codes = [event["code"] for event in payload["events"]]
    assert len(codes) == len(set(codes))
    assert "mission.received" in codes
    assert "mission.completed" in codes
    assert "password" not in response.text.lower()
    assert "authorization" not in response.text.lower()
