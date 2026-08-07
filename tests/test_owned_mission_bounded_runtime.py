from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import LocalAuthProvider, PasswordHasher, SQLiteUserRepository, UserRole
from app.auth_api import CSRF_COOKIE, CSRF_HEADER, get_auth_provider, router as auth_router
from app.mission_api import get_mission_repository, router as mission_router
from app.mission_sqlite import SQLiteMissionRepository
from app.models import SiteAnalysis


def _analysis() -> SiteAnalysis:
    return SiteAnalysis.model_validate(
        {
            "url": "https://example.org",
            "company_name": "Example Company",
            "business_summary": "Example business summary",
            "commercial_opportunity": {
                "opportunity_type": "AI automation",
                "problem_hypothesis": "Manual work",
                "recommended_solution": "Bounded AI assistant",
                "expected_value": "Faster processing",
                "score": 80,
                "qualification": "Приоритетная",
            },
            "agents": [
                {"name": "Agent 1", "purpose": "One", "benefit": "Benefit 1", "priority": "Высокий"},
                {"name": "Agent 2", "purpose": "Two", "benefit": "Benefit 2", "priority": "Средний"},
                {"name": "Agent 3", "purpose": "Three", "benefit": "Benefit 3", "priority": "Низкий"},
            ],
            "action_package": {
                "decision_maker_hypothesis": "Owner",
                "contact_reason": "Automation opportunity",
                "demo_scenario": ["Show bounded workflow"],
                "first_message": "Hello",
                "next_action": "Schedule demo",
            },
        }
    )


def _app(tmp_path):
    users = SQLiteUserRepository(tmp_path / "auth.sqlite3")
    hasher = PasswordHasher()
    users.create_user("alice", hasher.hash("test password 123"), UserRole.USER)
    users.create_user("bob", hasher.hash("test password 456"), UserRole.USER)
    auth = LocalAuthProvider(users)
    missions = SQLiteMissionRepository(tmp_path / "missions.sqlite3")
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(mission_router)
    app.dependency_overrides[get_auth_provider] = lambda: auth
    app.dependency_overrides[get_mission_repository] = lambda: missions
    return app, missions


def _login(client: TestClient, username: str, password: str) -> None:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200


def _csrf(client: TestClient) -> dict[str, str]:
    return {CSRF_HEADER: client.cookies[CSRF_COOKIE]}


def test_workspace_mission_runs_real_bounded_worker_and_persists_report(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIMETON_COOKIE_SECURE", "false")

    async def fake_fetch_site(url: str):
        return {"final_url": url, "title": "Example", "text": "Example text"}

    async def fake_analysis(final_url: str, title: str, text: str):
        return _analysis()

    monkeypatch.setattr("app.mission_bounded_runtime.fetch_site", fake_fetch_site)
    monkeypatch.setattr("app.mission_bounded_runtime.run_enriched_site_analysis", fake_analysis)

    app, repository = _app(tmp_path)
    client = TestClient(app)
    _login(client, "alice", "test password 123")

    created = client.post(
        "/api/user/missions",
        json={
            "title": "Audit example.org",
            "target_ref": "https://example.org",
            "input_snapshot": {"source": "test"},
            "correlation_id": "corr-owned-real-runtime",
        },
        headers=_csrf(client),
    )
    assert created.status_code == 201
    mission_id = created.json()["id"]
    assert created.json()["state"] == "running"

    mission = client.get(f"/api/user/missions/{mission_id}")
    assert mission.status_code == 200
    assert mission.json()["state"] == "completed"

    records = repository.records_for_owner(1, mission_id)
    assert records is not None
    summaries = [
        record["payload"].get("summary")
        for record in records
        if record["kind"] == "turn"
    ]
    assert summaries == [
        "execution_started",
        "planning_started",
        "site_fetch_started",
        "site_fetch_completed",
        "analysis_completed",
    ]
    assert "runtime_step_not_configured" not in summaries

    report = client.get(f"/api/user/missions/{mission_id}/report")
    assert report.status_code == 200
    assert report.json()["company_name"] == "Example Company"
    assert report.json()["mission_id"] == mission_id


def test_owned_report_is_not_visible_to_another_user(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIMETON_COOKIE_SECURE", "false")

    async def fake_fetch_site(url: str):
        return {"final_url": url, "title": "Example", "text": "Example text"}

    async def fake_analysis(final_url: str, title: str, text: str):
        return _analysis()

    monkeypatch.setattr("app.mission_bounded_runtime.fetch_site", fake_fetch_site)
    monkeypatch.setattr("app.mission_bounded_runtime.run_enriched_site_analysis", fake_analysis)

    app, _repository = _app(tmp_path)
    alice = TestClient(app)
    bob = TestClient(app)
    _login(alice, "alice", "test password 123")
    _login(bob, "bob", "test password 456")

    created = alice.post(
        "/api/user/missions",
        json={
            "title": "Private audit",
            "target_ref": "https://example.org",
            "input_snapshot": {},
            "correlation_id": "corr-owner-isolation",
        },
        headers=_csrf(alice),
    )
    mission_id = created.json()["id"]

    assert alice.get(f"/api/user/missions/{mission_id}/report").status_code == 200
    hidden = bob.get(f"/api/user/missions/{mission_id}/report")
    assert hidden.status_code == 404
    assert hidden.json()["detail"]["reason"] == "mission_not_found"


def test_bounded_worker_reports_typed_failure_instead_of_placeholder_block(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIMETON_COOKIE_SECURE", "false")

    async def failing_fetch_site(url: str):
        raise ValueError("synthetic fetch failure")

    monkeypatch.setattr("app.mission_bounded_runtime.fetch_site", failing_fetch_site)

    app, repository = _app(tmp_path)
    client = TestClient(app)
    _login(client, "alice", "test password 123")
    created = client.post(
        "/api/user/missions",
        json={
            "title": "Failing audit",
            "target_ref": "https://example.org",
            "input_snapshot": {},
            "correlation_id": "corr-owned-failure",
        },
        headers=_csrf(client),
    )
    mission_id = created.json()["id"]

    mission = client.get(f"/api/user/missions/{mission_id}").json()
    assert mission["state"] == "blocked"
    records = repository.records_for_owner(1, mission_id)
    assert records is not None
    terminal = [record for record in records if record["kind"] == "turn"][-1]["payload"]
    assert terminal["summary"] == "analysis_failed"
    assert terminal["reason_code"] == "site_analysis_failed"
    assert terminal["next_action"] == "verify_target_and_retry"
