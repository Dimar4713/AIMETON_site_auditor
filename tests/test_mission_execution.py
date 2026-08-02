from app.mission_contract import MissionCreate, MissionState
from app.mission_execution import start_mission_execution
from app.mission_sqlite import SQLiteMissionRepository


def request() -> MissionCreate:
    return MissionCreate(
        title="Live interface test",
        target_ref="https://example.test",
        correlation_id="corr-live-interface",
    )


def test_running_requires_persisted_execution_start_event(tmp_path) -> None:
    repository = SQLiteMissionRepository(tmp_path / "missions.sqlite3")
    mission = repository.create(101, request())

    result = start_mission_execution(repository, owner_id=101, mission=mission)

    assert result.started is True
    assert result.reason == "execution_started"
    assert result.event_id
    assert result.mission.state is MissionState.RUNNING
    records = repository.records_for_owner(101, mission.id)
    assert records is not None
    assert records[0]["kind"] == "turn"
    assert records[0]["payload"]["status"] == "running"
    assert records[0]["payload"]["summary"] == "execution_started"


def test_owner_mismatch_cannot_start_execution(tmp_path) -> None:
    repository = SQLiteMissionRepository(tmp_path / "missions.sqlite3")
    mission = repository.create(101, request())

    result = start_mission_execution(repository, owner_id=202, mission=mission)

    assert result.started is False
    assert result.reason == "mission_owner_mismatch"
    assert repository.get_for_owner(101, mission.id).state is MissionState.CREATED
    assert repository.records_for_owner(101, mission.id) == []


def test_non_created_mission_cannot_receive_second_start(tmp_path) -> None:
    repository = SQLiteMissionRepository(tmp_path / "missions.sqlite3")
    mission = repository.create(101, request())
    first = start_mission_execution(repository, owner_id=101, mission=mission)

    second = start_mission_execution(repository, owner_id=101, mission=first.mission)

    assert second.started is False
    assert second.reason == "mission_state_not_created"
    records = repository.records_for_owner(101, mission.id)
    assert records is not None
    assert len(records) == 1


class FailingStartRepository(SQLiteMissionRepository):
    def append_record(self, *args, **kwargs):
        raise RuntimeError("synthetic persistence failure")


def test_start_persistence_failure_is_typed_and_fail_closed(tmp_path) -> None:
    repository = FailingStartRepository(tmp_path / "missions.sqlite3")
    mission = repository.create(101, request())

    result = start_mission_execution(repository, owner_id=101, mission=mission)

    assert result.started is False
    assert result.reason == "execution_start_persistence_failed"
    assert result.mission.state is MissionState.BLOCKED
    assert repository.get_for_owner(101, mission.id).state is MissionState.BLOCKED
