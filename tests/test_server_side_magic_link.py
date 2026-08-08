from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.admin_users import AdminSQLiteUserRepository
from app.auth import PasswordHasher, UserRole
from app.auth_api import CSRF_COOKIE, CSRF_HEADER, router


def build_app(tmp_path, monkeypatch):
    database = tmp_path / "auth.sqlite3"
    monkeypatch.setenv("AIMETON_AUTH_DB", str(database))
    monkeypatch.setenv("AIMETON_COOKIE_SECURE", "false")
    repository = AdminSQLiteUserRepository(database)
    hasher = PasswordHasher()
    repository.create_user("admin", hasher.hash("admin secure password"), UserRole.ADMIN)
    repository.create_user("reviewer", hasher.hash("reviewer secure pass"), UserRole.USER)
    app = FastAPI()
    app.include_router(router)
    return app


def issue_reviewer_link(app: FastAPI):
    admin = TestClient(app)
    login = admin.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin secure password"},
    )
    assert login.status_code == 200
    response = admin.post(
        "/api/auth/admin/temporary-access-tokens",
        headers={CSRF_HEADER: admin.cookies[CSRF_COOKIE]},
        json={
            "subject_user_id": 2,
            "label": "Perplexity product reviewer",
            "purpose": "agent",
            "ttl_minutes": 60,
            "max_uses": 3,
            "reason": "server-side agent acceptance",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_issued_access_exposes_server_side_magic_link_path(tmp_path, monkeypatch):
    app = build_app(tmp_path, monkeypatch)
    issued = issue_reviewer_link(app)
    assert issued["magic_link_path"] == f'/api/auth/access/{issued["token"]}'
    assert issued["magic_link_fragment"] == f'#access_token={issued["token"]}'


def test_server_side_magic_link_sets_normal_session_and_redirects_without_js(tmp_path, monkeypatch):
    app = build_app(tmp_path, monkeypatch)
    issued = issue_reviewer_link(app)

    reviewer = TestClient(app, follow_redirects=False)
    opened = reviewer.get(issued["magic_link_path"])

    assert opened.status_code == 303
    assert opened.headers["location"] == "/"
    assert opened.headers["cache-control"] == "no-store"
    assert opened.headers["referrer-policy"] == "no-referrer"
    assert "aimeton_session" in reviewer.cookies
    assert "aimeton_csrf" in reviewer.cookies

    me = reviewer.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "reviewer"
    assert me.json()["role"] == "user"


def test_server_side_magic_link_invalid_token_is_generic_unauthenticated(tmp_path, monkeypatch):
    app = build_app(tmp_path, monkeypatch)
    reviewer = TestClient(app, follow_redirects=False)
    response = reviewer.get("/api/auth/access/" + "x" * 40)
    assert response.status_code == 401
    assert response.json()["detail"] == {"reason": "unauthenticated"}
    assert "aimeton_session" not in reviewer.cookies
