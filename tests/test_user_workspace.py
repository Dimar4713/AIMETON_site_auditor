from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import User, UserRole
from app.auth_api import current_user
from app.workspace_api import router


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


def _user() -> User:
    return User(
        id=42,
        username="workspace-user",
        role=UserRole.USER,
        is_active=True,
    )


def test_login_page_is_public() -> None:
    response = TestClient(_app()).get("/login")
    assert response.status_code == 200
    assert "Вход в рабочее пространство" in response.text


def test_workspace_requires_authenticated_session() -> None:
    response = TestClient(_app()).get("/workspace")
    assert response.status_code == 401
    assert response.json()["detail"]["reason"] == "unauthenticated"


def test_workspace_serves_shell_for_authenticated_user() -> None:
    app = _app()
    app.dependency_overrides[current_user] = _user
    response = TestClient(app).get("/workspace")
    assert response.status_code == 200
    assert "Мои миссии" in response.text
    assert "/static/workspace.js" in response.text


def test_mission_detail_shell_requires_authenticated_session() -> None:
    response = TestClient(_app()).get("/workspace/missions/mission_unknown")
    assert response.status_code == 401
    assert response.json()["detail"]["reason"] == "unauthenticated"


def test_mission_detail_shell_uses_owner_scoped_client_api() -> None:
    app = _app()
    app.dependency_overrides[current_user] = _user
    response = TestClient(app).get("/workspace/missions/mission_example")
    assert response.status_code == 200
    assert "/static/mission-detail.js" in response.text
    source = open("static/mission-detail.js", encoding="utf-8").read()
    assert "/api/user/missions/" in source
    assert "/api/admin/" not in source
    assert "owner_id" not in source
    assert "technical_snapshot" not in source


def test_workspace_client_uses_owned_api_and_server_session() -> None:
    source = open("static/workspace.js", encoding="utf-8").read()
    assert "/api/auth/me" in source
    assert "/api/user/missions" in source
    assert "X-CSRF-Token" in source
    assert "owner_id" not in source
    assert "/api/admin/" not in source
    assert "/workspace/missions/" in source
