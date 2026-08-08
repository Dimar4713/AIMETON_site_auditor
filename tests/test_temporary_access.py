from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.admin_users import AdminSQLiteUserRepository
from app.auth import PasswordHasher, UserRole
from app.auth_api import CSRF_COOKIE, CSRF_HEADER, router


def build_client(tmp_path, monkeypatch):
    database = tmp_path / "auth.sqlite3"
    monkeypatch.setenv("AIMETON_AUTH_DB", str(database))
    monkeypatch.setenv("AIMETON_COOKIE_SECURE", "false")
    repository = AdminSQLiteUserRepository(database)
    hasher = PasswordHasher()
    repository.create_user("admin", hasher.hash("admin secure password"), UserRole.ADMIN)
    repository.create_user("reviewer", hasher.hash("reviewer secure pass"), UserRole.USER)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app), repository


def login_admin(client: TestClient):
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin secure password"},
    )
    assert response.status_code == 200
    return {CSRF_HEADER: client.cookies[CSRF_COOKIE]}


def issue_token(client: TestClient, headers, *, max_uses=1, ttl_minutes=60):
    response = client.post(
        "/api/auth/admin/temporary-access-tokens",
        headers=headers,
        json={
            "subject_user_id": 2,
            "label": "Perplexity product reviewer",
            "purpose": "agent",
            "ttl_minutes": ttl_minutes,
            "max_uses": max_uses,
            "reason": "independent product acceptance",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_single_use_token_creates_normal_session_once(tmp_path, monkeypatch):
    admin_client, _repository = build_client(tmp_path, monkeypatch)
    headers = login_admin(admin_client)
    issued = issue_token(admin_client, headers, max_uses=1)
    assert issued["token"].startswith("aimeton_tmp_")
    assert issued["magic_link_fragment"] == f'#access_token={issued["token"]}'

    reviewer = TestClient(admin_client.app)
    first = reviewer.post("/api/auth/token-login", json={"token": issued["token"]})
    assert first.status_code == 200
    assert first.json()["username"] == "reviewer"
    assert first.json()["remaining_uses"] == 0
    assert reviewer.get("/api/auth/me").status_code == 200

    second_browser = TestClient(admin_client.app)
    second = second_browser.post("/api/auth/token-login", json={"token": issued["token"]})
    assert second.status_code == 401
    assert second.json()["detail"] == {"reason": "unauthenticated"}


def test_admin_listing_never_returns_secret_or_digest(tmp_path, monkeypatch):
    client, _repository = build_client(tmp_path, monkeypatch)
    headers = login_admin(client)
    issued = issue_token(client, headers, max_uses=3)

    listing = client.get("/api/auth/admin/temporary-access-tokens")
    assert listing.status_code == 200
    serialized = listing.text
    assert issued["token"] not in serialized
    assert "token_digest" not in serialized
    assert "token" not in listing.json()[0]


def test_revocation_invalidates_sessions_created_by_token(tmp_path, monkeypatch):
    admin_client, _repository = build_client(tmp_path, monkeypatch)
    headers = login_admin(admin_client)
    issued = issue_token(admin_client, headers, max_uses=5)

    reviewer = TestClient(admin_client.app)
    login = reviewer.post("/api/auth/token-login", json={"token": issued["token"]})
    assert login.status_code == 200
    assert reviewer.get("/api/auth/me").status_code == 200

    revoked = admin_client.post(
        f'/api/auth/admin/temporary-access-tokens/{issued["id"]}/revoke',
        headers=headers,
        json={"reason": "review window closed"},
    )
    assert revoked.status_code == 204
    assert reviewer.get("/api/auth/me").status_code == 401
    assert reviewer.post("/api/auth/token-login", json={"token": issued["token"]}).status_code == 401


def test_temporary_access_session_never_outlives_credential(tmp_path, monkeypatch):
    admin_client, repository = build_client(tmp_path, monkeypatch)
    headers = login_admin(admin_client)
    issued = issue_token(admin_client, headers, max_uses=2, ttl_minutes=5)

    reviewer = TestClient(admin_client.app)
    login = reviewer.post("/api/auth/token-login", json={"token": issued["token"]})
    assert login.status_code == 200

    session_token = reviewer.cookies["aimeton_session"]
    token_hash = __import__("hashlib").sha256(session_token.encode("utf-8")).hexdigest()
    with repository._connect() as connection:
        session_row = connection.execute(
            "SELECT expires_at FROM sessions WHERE token_hash = ?", (token_hash,)
        ).fetchone()
    assert session_row is not None
    session_expiry = datetime.fromisoformat(session_row["expires_at"])
    credential_expiry = datetime.fromisoformat(issued["expires_at"])
    assert session_expiry <= credential_expiry
    assert session_expiry > datetime.now(UTC)


def test_temporary_access_cannot_target_admin(tmp_path, monkeypatch):
    client, _repository = build_client(tmp_path, monkeypatch)
    headers = login_admin(client)
    response = client.post(
        "/api/auth/admin/temporary-access-tokens",
        headers=headers,
        json={
            "subject_user_id": 1,
            "label": "forbidden admin token",
            "purpose": "agent",
            "ttl_minutes": 60,
            "max_uses": 1,
            "reason": "security regression test",
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"] == {"reason": "temporary_access_forbidden"}


def test_magic_link_frontend_removes_secret_and_never_persists_it():
    source = open("static/auth-ui.js", encoding="utf-8").read()
    assert "#access_token" not in source
    assert "params.get('access_token')" in source
    assert "history.replaceState" in source
    assert "/api/auth/token-login" in source
    assert "localStorage.setItem" not in source
    assert "sessionStorage.setItem" not in source
