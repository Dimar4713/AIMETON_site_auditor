from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import LocalAuthProvider, PasswordHasher, SQLiteUserRepository, UserRole
from app.auth_api import CSRF_COOKIE, CSRF_HEADER, get_auth_provider, router as auth_router
from app.mission_api import get_mission_repository, router as mission_router
from app.mission_sqlite import SQLiteMissionRepository


def build_client(tmp_path, monkeypatch):
    monkeypatch.setenv("AIMETON_COOKIE_SECURE", "false")

    async def noop_owned_worker(repository, *, owner_id, mission):
        return None

    monkeypatch.setattr("app.mission_api.run_owned_site_analysis", noop_owned_worker)
    users = SQLiteUserRepository(tmp_path / "auth.sqlite3")
    hasher = PasswordHasher()
    users.create_user("admin", hasher.hash("admin secure password"), UserRole.ADMIN)
    users.create_user("alice", hasher.hash("alice secure password"), UserRole.USER)
    users.create_user("bob", hasher.hash("bob secure password"), UserRole.USER)
    auth = LocalAuthProvider(users)
    missions = SQLiteMissionRepository(tmp_path / "missions.sqlite3")

    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(mission_router)
    app.dependency_overrides[get_auth_provider] = lambda: auth
    app.dependency_overrides[get_mission_repository] = lambda: missions
    return TestClient(app), missions


def login(client: TestClient, username: str, password: str) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200


def csrf_headers(client: TestClient) -> dict[str, str]:
    return {CSRF_HEADER: client.cookies[CSRF_COOKIE]}


def mission_payload() -> dict[str, object]:
    return {
        "title": "Audit example.org",
        "target_ref": "https://example.org",
        "input_snapshot": {"internal_seed": "must-not-leak"},
        "correlation_id": "corr-owned-1",
        "owner_id": 999999,
    }


def test_create_uses_session_actor_and_safe_projection(tmp_path, monkeypatch):
    client, repository = build_client(tmp_path, monkeypatch)
    login(client, "alice", "alice secure password")

    response = client.post(
        "/api/user/missions",
        json=mission_payload(),
        headers=csrf_headers(client),
    )

    assert response.status_code == 201
    payload = response.json()
    assert "owner_id" not in payload
    assert "input_snapshot" not in payload
    assert "technical_snapshot" not in payload
    stored = repository.get_for_admin(payload["id"])
    assert stored is not None
    assert stored.owner_id == 2


def test_mission_mutations_require_csrf(tmp_path, monkeypatch):
    client, _repository = build_client(tmp_path, monkeypatch)
    login(client, "alice", "alice secure password")

    response = client.post("/api/user/missions", json=mission_payload())

    assert response.status_code == 403
    assert response.json()["detail"] == {"reason": "csrf_failed"}


def test_cross_user_read_list_and_write_are_hidden(tmp_path, monkeypatch):
    client, _repository = build_client(tmp_path, monkeypatch)
    login(client, "alice", "alice secure password")
    created = client.post(
        "/api/user/missions",
        json=mission_payload(),
        headers=csrf_headers(client),
    )
    mission_id = created.json()["id"]

    login(client, "bob", "bob secure password")

    assert client.get("/api/user/missions").json() == []
    hidden = client.get(f"/api/user/missions/{mission_id}")
    assert hidden.status_code == 404
    assert hidden.json()["detail"] == {"reason": "mission_not_found"}

    mutation = client.patch(
        f"/api/user/missions/{mission_id}/state",
        json={"state": "completed"},
        headers=csrf_headers(client),
    )
    assert mutation.status_code == 404
    assert mutation.json()["detail"] == {"reason": "mission_not_found"}


def test_owner_can_update_state_without_exposing_internal_fields(tmp_path, monkeypatch):
    client, _repository = build_client(tmp_path, monkeypatch)
    login(client, "alice", "alice secure password")
    created = client.post(
        "/api/user/missions",
        json=mission_payload(),
        headers=csrf_headers(client),
    )
    mission_id = created.json()["id"]

    updated = client.patch(
        f"/api/user/missions/{mission_id}/state",
        json={"state": "degraded"},
        headers=csrf_headers(client),
    )

    assert updated.status_code == 200
    assert updated.json()["state"] == "degraded"
    assert "owner_id" not in updated.json()
    assert "technical_snapshot" not in updated.json()


def test_admin_access_uses_admin_policy_boundary(tmp_path, monkeypatch):
    client, _repository = build_client(tmp_path, monkeypatch)
    login(client, "alice", "alice secure password")
    created = client.post(
        "/api/user/missions",
        json=mission_payload(),
        headers=csrf_headers(client),
    )
    mission_id = created.json()["id"]

    denied = client.get("/api/admin/missions")
    assert denied.status_code == 403
    assert denied.json()["detail"] == {"reason": "role_forbidden"}

    login(client, "admin", "admin secure password")
    listing = client.get("/api/admin/missions")
    assert listing.status_code == 200
    assert listing.json()[0]["id"] == mission_id
    assert listing.json()[0]["owner_id"] == 2

    detail = client.get(f"/api/admin/missions/{mission_id}")
    assert detail.status_code == 200
    assert detail.json()["owner_id"] == 2
    assert "technical_snapshot" not in detail.json()
