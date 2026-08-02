from pathlib import Path

from app.admin_mission_retry import AdminMissionRetryService, RetryFailure
from app.auth import User, UserRole
from app.mission_contract import MissionCreate, MissionState
from app.mission_sqlite import SQLiteMissionRepository


def _admin() -> User:
    return User(id=1, username="admin", role=UserRole.ADMIN, is_active=True)


def _mission(repository: SQLiteMissionRepository, state: MissionState):
    mission = repository.create(
        2,
        MissionCreate(
            title="Retry target",
            target_ref="https://example.test",
            input_snapshot={},
            correlation_id="retry-test",
        ),
    )
    updated = repository.update_state_for_owner(2, mission.id, state)
    assert updated is not None
    return updated


def test_retry_resumes_only_blocked_or_degraded_and_persists_audit(tmp_path: Path) -> None:
    repository = SQLiteMissionRepository(tmp_path / "missions.sqlite3")
    mission = _mission(repository, MissionState.BLOCKED)
    service = AdminMissionRetryService(repository)

    decision = service.retry(mission.id, _admin(), "resume", "provider recovered")

    assert decision.failure is None
    assert decision.mission is not None
    assert decision.mission.state is MissionState.RUNNING
    reopened = AdminMissionRetryService(SQLiteMissionRepository(repository.path))
    events = reopened.list_events()
    assert events[0]["mission_id"] == mission.id
    assert events[0]["result"] == "success"
    assert "provider recovered" in events[0]["reason"]


def test_retry_rejects_unknown_action_and_non_retryable_state(tmp_path: Path) -> None:
    repository = SQLiteMissionRepository(tmp_path / "missions.sqlite3")
    mission = _mission(repository, MissionState.COMPLETED)
    service = AdminMissionRetryService(repository)

    unknown = service.retry(mission.id, _admin(), "rerun_all", "not allow-listed")
    completed = service.retry(mission.id, _admin(), "resume", "completed must stay closed")

    assert unknown.failure is RetryFailure.ACTION_NOT_ALLOWED
    assert completed.failure is RetryFailure.STATE_NOT_RETRYABLE
    assert repository.get_for_admin(mission.id).state is MissionState.COMPLETED
    assert {event["result"] for event in service.list_events()} == {
        RetryFailure.ACTION_NOT_ALLOWED.value,
        RetryFailure.STATE_NOT_RETRYABLE.value,
    }


def test_retry_audit_projection_excludes_internal_mission_data(tmp_path: Path) -> None:
    repository = SQLiteMissionRepository(tmp_path / "missions.sqlite3")
    mission = _mission(repository, MissionState.DEGRADED)
    service = AdminMissionRetryService(repository)
    service.retry(mission.id, _admin(), "resume", "safe retry")

    event = service.list_events()[0]
    assert set(event) == {"id", "mission_id", "actor_id", "action", "reason", "result", "created_at"}
    for forbidden in ("technical_snapshot", "input_snapshot", "password_hash", "token", "storage_path"):
        assert forbidden not in event
