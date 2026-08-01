from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import LocalAuthProvider, PasswordHasher, SQLiteUserRepository, UserRole
from app.auth_api import get_auth_provider, router


def build_client(tmp_path):
    repository = SQLiteUserRepository(tmp_path / "auth.sqlite3")
    hasher = PasswordHasher()
    repository.create_user("admin", hasher.hash("admin secure password"), UserRole.ADMIN)
    repository.create_user("analyst", hasher.hash("analyst secure pass"), UserRole.USER)
    auth = LocalAuthProvider(repository)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_auth_provider] = lambda: auth
    return TestClient(app), repository


def test_login_me_and_logout(tmp_path, monkeypatch):
    monkeypatch.setenv("AIMETON_COOKIE_SECURE", "false")
    client, _repository = build_client(tmp_path)

    login = client.post(
        "/api/auth/login",
        json={"username": "analyst", "password": "analyst secure pass"},
    )
    assert login.status_code == 200
    assert login.json() == {"id": 2, "username": "analyst", "role": "user"}
    assert "httponly" in login.headers["set-cookie"].lower()
    assert "samesite=strict" in login.headers["set-cookie"].lower()

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "analyst"

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_invalid_credentials_are_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("AIMETON_COOKIE_SECURE", "false")
    client, _repository = build_client(tmp_path)
    response = client.post(
        "/api/auth/login",
        json={"username": "analyst", "password": "incorrect password"},
    )
    assert response.status_code == 401
    assert "aimeton_session" not in response.headers.get("set-cookie", "")


def test_user_cannot_access_admin_route(tmp_path, monkeypatch):
    monkeypatch.setenv("AIMETON_COOKIE_SECURE", "false")
    client, _repository = build_client(tmp_path)
    client.post(
        "/api/auth/login",
        json={"username": "analyst", "password": "analyst secure pass"},
    )
    assert client.get("/api/auth/admin/ping").status_code == 403


def test_admin_can_access_admin_route(tmp_path, monkeypatch):
    monkeypatch.setenv("AIMETON_COOKIE_SECURE", "false")
    client, _repository = build_client(tmp_path)
    client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin secure password"},
    )
    response = client.get("/api/auth/admin/ping")
    assert response.status_code == 200
    assert response.json()["role"] == "admin"


def test_blocked_user_loses_active_session(tmp_path, monkeypatch):
    monkeypatch.setenv("AIMETON_COOKIE_SECURE", "false")
    client, repository = build_client(tmp_path)
    client.post(
        "/api/auth/login",
        json={"username": "analyst", "password": "analyst secure pass"},
    )
    repository.set_active(2, False)
    assert client.get("/api/auth/me").status_code == 401
