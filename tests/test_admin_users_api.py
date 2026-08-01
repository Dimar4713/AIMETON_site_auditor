from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.admin_users import AdminSQLiteUserRepository
from app.auth import PasswordHasher, UserRole
from app.auth_api import CSRF_COOKIE, CSRF_HEADER, get_auth_provider, router
from app.session_resolution import TypedLocalAuthProvider


def build_client(tmp_path):
    repository = AdminSQLiteUserRepository(tmp_path / "auth.sqlite3")
    hasher = PasswordHasher()
    repository.create_user("admin", hasher.hash("admin secure password"), UserRole.ADMIN)
    repository.create_user("analyst", hasher.hash("analyst secure pass"), UserRole.USER)
    auth = TypedLocalAuthProvider(repository)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_auth_provider] = lambda: auth
    return TestClient(app), repository


def login(client: TestClient, username: str, password: str) -> str:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    token = client.cookies.get(CSRF_COOKIE)
    assert token
    return token


def test_regular_user_cannot_use_admin_user_api(tmp_path, monkeypatch):
    monkeypatch.setenv("AIMETON_COOKIE_SECURE", "false")
    client, _repository = build_client(tmp_path)
    csrf = login(client, "analyst", "analyst secure pass")
    response = client.post(
        "/api/auth/admin/users",
        headers={CSRF_HEADER: csrf},
        json={"username": "other", "password": "other secure password", "role": "user", "reason": "test"},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["reason"] == "role_forbidden"


def test_admin_user_lifecycle_is_safe_and_audited(tmp_path, monkeypatch):
    monkeypatch.setenv("AIMETON_COOKIE_SECURE", "false")
    client, repository = build_client(tmp_path)
    csrf = login(client, "admin", "admin secure password")

    created = client.post(
        "/api/auth/admin/users",
        headers={CSRF_HEADER: csrf},
        json={
            "username": "New.User@Example.COM ",
            "password": "initial secure password",
            "role": "user",
            "reason": "onboarding",
        },
    )
    assert created.status_code == 201
    user = created.json()
    assert user["username"] == "new.user@example.com"
    assert user["is_active"] is True
    assert "password" not in created.text.lower()
    assert "hash" not in created.text.lower()
    user_id = user["id"]

    listed = client.get("/api/auth/admin/users")
    assert listed.status_code == 200
    assert any(item["id"] == user_id for item in listed.json())
    assert "password_hash" not in listed.text

    blocked = client.patch(
        f"/api/auth/admin/users/{user_id}/state",
        headers={CSRF_HEADER: csrf},
        json={"active": False, "reason": "security review"},
    )
    assert blocked.status_code == 200
    assert blocked.json()["is_active"] is False

    unblocked = client.patch(
        f"/api/auth/admin/users/{user_id}/state",
        headers={CSRF_HEADER: csrf},
        json={"active": True, "reason": "review complete"},
    )
    assert unblocked.status_code == 200
    assert unblocked.json()["is_active"] is True

    reset = client.post(
        f"/api/auth/admin/users/{user_id}/reset-password",
        headers={CSRF_HEADER: csrf},
        json={"password": "replacement secure password", "reason": "credential rotation"},
    )
    assert reset.status_code == 204
    assert "replacement secure password" not in reset.text

    separate = TestClient(client.app)
    old_login = separate.post(
        "/api/auth/login",
        json={"username": "new.user@example.com", "password": "initial secure password"},
    )
    assert old_login.status_code == 401
    new_login = separate.post(
        "/api/auth/login",
        json={"username": "new.user@example.com", "password": "replacement secure password"},
    )
    assert new_login.status_code == 200

    with repository._connect() as connection:
        events = connection.execute(
            "SELECT action, reason, result FROM auth_audit_events ORDER BY id"
        ).fetchall()
    assert [(row["action"], row["result"]) for row in events] == [
        ("create_user", "success"),
        ("set_active", "success"),
        ("set_active", "success"),
        ("reset_password", "success"),
    ]
    assert all(row["reason"] for row in events)


def test_admin_mutation_requires_csrf_and_self_block_is_denied(tmp_path, monkeypatch):
    monkeypatch.setenv("AIMETON_COOKIE_SECURE", "false")
    client, _repository = build_client(tmp_path)
    csrf = login(client, "admin", "admin secure password")

    missing = client.post(
        "/api/auth/admin/users",
        json={"username": "other", "password": "other secure password", "role": "user", "reason": "test"},
    )
    assert missing.status_code == 403
    assert missing.json()["detail"]["reason"] == "csrf_failed"

    denied = client.patch(
        "/api/auth/admin/users/1/state",
        headers={CSRF_HEADER: csrf},
        json={"active": False, "reason": "mistake"},
    )
    assert denied.status_code == 409
    assert denied.json()["detail"]["reason"] == "self_block_denied"
