from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import LocalAuthProvider, PasswordHasher, SQLiteUserRepository, UserRole
from app.auth_api import (
    CSRF_COOKIE,
    CSRF_HEADER,
    SESSION_COOKIE,
    get_auth_provider,
    router,
)


def build_client(tmp_path):
    repository = SQLiteUserRepository(tmp_path / "auth.sqlite3")
    hasher = PasswordHasher()
    repository.create_user("admin", hasher.hash("admin secure password"), UserRole.ADMIN)
    repository.create_user("analyst", hasher.hash("analyst secure pass"), UserRole.USER)
    auth = LocalAuthProvider(repository)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_auth_provider] = lambda: auth
    return TestClient(app), repository, auth


def login_as(client: TestClient, username: str, password: str):
    return client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )


def csrf_headers(client: TestClient) -> dict[str, str]:
    return {CSRF_HEADER: client.cookies[CSRF_COOKIE]}


def test_login_me_and_logout(tmp_path, monkeypatch):
    monkeypatch.setenv("AIMETON_COOKIE_SECURE", "false")
    client, _repository, _auth = build_client(tmp_path)

    login = login_as(client, "analyst", "analyst secure pass")
    assert login.status_code == 200
    assert login.json() == {"id": 2, "username": "analyst", "role": "user"}
    set_cookie = login.headers.get_list("set-cookie")
    assert any(SESSION_COOKIE in value and "httponly" in value.lower() for value in set_cookie)
    assert any(CSRF_COOKIE in value and "httponly" not in value.lower() for value in set_cookie)
    assert all("samesite=strict" in value.lower() for value in set_cookie)
    assert SESSION_COOKIE in client.cookies
    assert CSRF_COOKIE in client.cookies

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "analyst"

    logout = client.post("/api/auth/logout", headers=csrf_headers(client))
    assert logout.status_code == 204
    assert SESSION_COOKIE not in client.cookies
    assert CSRF_COOKIE not in client.cookies
    assert client.get("/api/auth/me").status_code == 401


def test_logout_rejects_missing_or_wrong_csrf(tmp_path, monkeypatch):
    monkeypatch.setenv("AIMETON_COOKIE_SECURE", "false")
    client, _repository, _auth = build_client(tmp_path)
    login_as(client, "analyst", "analyst secure pass")

    missing = client.post("/api/auth/logout")
    assert missing.status_code == 403
    assert missing.json()["detail"] == {"reason": "csrf_failed"}
    assert SESSION_COOKIE in client.cookies

    wrong = client.post("/api/auth/logout", headers={CSRF_HEADER: "wrong-token"})
    assert wrong.status_code == 403
    assert wrong.json()["detail"] == {"reason": "csrf_failed"}
    assert SESSION_COOKIE in client.cookies


def test_login_rotates_and_revokes_preexisting_session(tmp_path, monkeypatch):
    monkeypatch.setenv("AIMETON_COOKIE_SECURE", "false")
    client, _repository, auth = build_client(tmp_path)

    first = login_as(client, "analyst", "analyst secure pass")
    assert first.status_code == 200
    old_token = client.cookies[SESSION_COOKIE]

    second = login_as(client, "analyst", "analyst secure pass")
    assert second.status_code == 200
    new_token = client.cookies[SESSION_COOKIE]

    assert new_token != old_token
    assert auth.resolve_session(old_token) is None
    assert auth.resolve_session(new_token) is not None


def test_logout_revokes_server_side_session(tmp_path, monkeypatch):
    monkeypatch.setenv("AIMETON_COOKIE_SECURE", "false")
    client, _repository, auth = build_client(tmp_path)
    login_as(client, "analyst", "analyst secure pass")
    token = client.cookies[SESSION_COOKIE]

    response = client.post("/api/auth/logout", headers=csrf_headers(client))
    assert response.status_code == 204
    assert auth.resolve_session(token) is None


def test_invalid_credentials_are_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("AIMETON_COOKIE_SECURE", "false")
    client, _repository, _auth = build_client(tmp_path)
    response = login_as(client, "analyst", "incorrect password")
    assert response.status_code == 401
    assert SESSION_COOKIE not in response.headers.get("set-cookie", "")
    assert CSRF_COOKIE not in response.headers.get("set-cookie", "")
    assert "password_hash" not in response.text


def test_user_cannot_access_admin_route(tmp_path, monkeypatch):
    monkeypatch.setenv("AIMETON_COOKIE_SECURE", "false")
    client, _repository, _auth = build_client(tmp_path)
    login_as(client, "analyst", "analyst secure pass")
    assert client.get("/api/auth/admin/ping").status_code == 403


def test_admin_can_access_admin_route(tmp_path, monkeypatch):
    monkeypatch.setenv("AIMETON_COOKIE_SECURE", "false")
    client, _repository, _auth = build_client(tmp_path)
    login_as(client, "admin", "admin secure password")
    response = client.get("/api/auth/admin/ping")
    assert response.status_code == 200
    assert response.json()["role"] == "admin"


def test_blocked_user_loses_active_session(tmp_path, monkeypatch):
    monkeypatch.setenv("AIMETON_COOKIE_SECURE", "false")
    client, repository, _auth = build_client(tmp_path)
    login_as(client, "analyst", "analyst secure pass")
    repository.set_active(2, False)
    assert client.get("/api/auth/me").status_code == 401
