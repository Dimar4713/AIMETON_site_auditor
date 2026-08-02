from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.admin_workspace_api import router
from app.auth import User, UserRole
from app.auth_api import require_admin


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


def test_admin_workspace_requires_admin() -> None:
    response = TestClient(_app()).get("/admin/workspace")
    assert response.status_code in {401, 403}


def test_admin_workspace_serves_shell_for_admin() -> None:
    app = _app()
    app.dependency_overrides[require_admin] = lambda: User(
        id=1,
        username="admin",
        role=UserRole.ADMIN,
        is_active=True,
    )
    response = TestClient(app).get("/admin/workspace")
    assert response.status_code == 200
    assert "Административное пространство" in response.text
    assert "/static/admin-workspace.js" in response.text


def test_admin_client_uses_only_safe_admin_boundaries() -> None:
    source = open("static/admin-workspace.js", encoding="utf-8").read()
    assert "/api/auth/admin/users" in source
    assert "/api/admin/missions" in source
    for forbidden in ("password_hash", "aimeton_session", "signed_url", "storage_path", "technical_snapshot"):
        assert forbidden not in source
