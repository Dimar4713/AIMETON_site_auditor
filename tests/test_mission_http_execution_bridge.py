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


def test_http_create_starts_execution_without_placeholder_terminal_block(tmp_path, monkeypatch) -> None:
    client, repository = build_client(tmp_path, monkeypatch)
    login(client)
    response = client.post(
        "/api/user/missions",
        json={
            "title": "Audit example.org",
            "target_ref": "https://example.org",
            "input_snapshot": {},
            "correlation_id": "corr-http-owned-runtime",
        },
        headers=csrf_headers(client),
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["state"] == "running"
    records = repository.records_for_owner(1, payload["id"])
    assert records is not None
    assert [record["payload"]["summary"] for record in records] == [
        "execution_started",
    ]


def test_http_records_do_not_claim_runtime_step_is_unconfigured(tmp_path, monkeypatch) -> None:
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
    summaries = [record["data"].get("summary") for record in response.json()["evidence"]]
    assert summaries == ["execution_started"]
    assert "runtime_step_not_configured" not in summaries
