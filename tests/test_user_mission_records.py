from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import User, UserRole
from app.auth_api import current_user
from app.mission_api import get_mission_repository, router


class FakeRepository:
    def records_for_owner(self, owner_id: int, mission_id: str):
        if owner_id != 7 or mission_id != "mission-own":
            return None
        return [
            {
                "id": "turn-1",
                "kind": "turn",
                "payload": {
                    "turn_id": "turn-1",
                    "status": "completed",
                    "summary": "Публичное резюме",
                    "secret": "must-not-leak",
                    "internal_trace": {"raw": True},
                },
                "digest": "abc",
                "created_at": "2026-08-02T00:00:00+00:00",
            },
            {
                "id": "udp-1",
                "kind": "sufficiency",
                "payload": {
                    "record_id": "udp-1",
                    "level": "L4",
                    "status": "sufficient",
                    "summary": "Достаточность подтверждена",
                    "provider_token": "must-not-leak",
                },
                "digest": "def",
                "created_at": "2026-08-02T00:01:00+00:00",
            },
            {
                "id": "report-1",
                "kind": "report_metadata",
                "payload": {
                    "report_id": "report-1",
                    "available": False,
                    "blocked_reason": "udp_below_release_threshold",
                    "storage_path": "/private/report.docx",
                },
                "digest": "ghi",
                "created_at": "2026-08-02T00:02:00+00:00",
            },
        ]


def app_client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[current_user] = lambda: User(
        id=7,
        username="workspace-user",
        role=UserRole.USER,
        is_active=True,
    )
    app.dependency_overrides[get_mission_repository] = FakeRepository
    return TestClient(app)


def test_records_projection_is_owner_scoped_and_sanitized() -> None:
    response = app_client().get("/api/user/missions/mission-own/records")
    assert response.status_code == 200
    body = response.json()
    assert body["mission_id"] == "mission-own"
    assert body["report_reason"] == "udp_below_release_threshold"
    rendered = response.text
    assert "must-not-leak" not in rendered
    assert "internal_trace" not in rendered
    assert "provider_token" not in rendered
    assert "storage_path" not in rendered
    assert body["evidence"][0]["data"]["summary"] == "Публичное резюме"
    assert body["evidence"][1]["data"]["level"] == "L4"


def test_foreign_records_are_indistinguishable_from_missing() -> None:
    response = app_client().get("/api/user/missions/mission-foreign/records")
    assert response.status_code == 404
    assert response.json()["detail"]["reason"] == "mission_not_found"


def test_workspace_client_reads_only_user_records_projection() -> None:
    source = open("static/mission-detail.js", encoding="utf-8").read()
    assert "/api/user/missions/" in source
    assert "/records" in source
    assert "/api/admin/" not in source
    assert "technical_snapshot" not in source
    assert "owner_id" not in source
