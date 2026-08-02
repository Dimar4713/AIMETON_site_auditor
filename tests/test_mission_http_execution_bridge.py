from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import LocalAuthProvider, PasswordHasher, SQLiteUserRepository, UserRole
from app.auth_api import CSRF_COOKIE, CSRF_HEADER, get_auth_provider, router as auth_router
from app.mission_api import get_mission_repository, router as mission_router
from app.mission_sqlite import SQLiteMissionRepository


def build_client(tmp_path, monkeypatch):
    monkeypatch.setenv("AIMETON_COOKIE_SECURE", "false")
    users = SQLiteUserRepository(tmp_path / "auth.sqlite3")
    hasher = PasswordHasher()
    users.create_user("alice", hasher.hash("test password 123"), UserRole.USER)
    auth = LocalAuthProvider(users)
    missions = SQLiteMissionRepository(tmp_path / "missions.sqlite3")
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(mission_router)
    app.dependency_overrides[get_auth_provider] = lambda: auth
    app.dependency_overrides[get_mission_repository] = lambda: missions
    return TestClient(app), missions


def login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "test password 123"},
    )
    assert response.status_code == 200


def csrf_headers(client: TestClient) -> dict[str, str]:
    return {CSRF_HEADER: client.cookies[CSRF_COOKIE]}


def test_http_create_runs_local_step_and_blocks_truthfully(tmp_path, monkeypatch) -> None:
    client, repository = build_client(tmp_path, monkeypatch)
    login(client)
    response = client.post(
        "/api/user/missions",
        json={
            "title": "Audit example.org",
            "target_ref": "https://example.org",
            "input_snapshot": {},
            "correlation_id": "corr-http-local-runtime",
        },
        headers=csrf_headers(client),
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["state"] == "blocked"
    records = repository.records_for_owner(1, payload["id"])
    assert records is not None
    assert [record["payload"]["summary"] for record in records] == [
        "execution_started",
        "planning_started",
        "runtime_step_not_configured",
    ]


def test_http_records_expose_typed_terminal_outcome(tmp_path, monkeypatch) -> None:
    client, _repository = build_client(tmp_path, monkeypatch)
    login(client)
    created = client.post(
        "/api/user/missions",
        json={
            "title": "Audit example.org",
            "target_ref": "https://example.org",
            "input_snapshot": {},
            "correlation_id": "corr-http-runtime-records",
        },
        headers=csrf_headers(client),
    )
    mission_id = created.json()["id"]
    response = client.get(f"/api/user/missions/{mission_id}/records")
    assert response.status_code == 200
    terminal = response.json()["evidence"][-1]["data"]
    assert terminal["status"] == "blocked"
    assert terminal["reason_code"] == "runtime_step_not_configured"
    assert terminal["next_action"] == "configure_bounded_runtime_worker"
