from app.mission_contract import MissionCreate, MissionState
from app.mission_execution import start_mission_execution
from app.mission_local_runtime import run_cost_free_local_step
from app.mission_sqlite import SQLiteMissionRepository


def request() -> MissionCreate:
    return MissionCreate(
        title="Audit example.org",
        target_ref="https://example.org",
        input_snapshot={},
        correlation_id="corr-local-runtime",
    )


def test_local_runtime_persists_planning_and_typed_terminal_event(tmp_path) -> None:
    repository = SQLiteMissionRepository(tmp_path / "missions.sqlite3")
    created = repository.create(1, request())
    started = start_mission_execution(repository, owner_id=1, mission=created)

    outcome = run_cost_free_local_step(
        repository,
        owner_id=1,
        mission=started.mission,
    )

    assert outcome.mission.state is MissionState.BLOCKED
    assert outcome.reason == "runtime_step_not_configured"
    records = repository.records_for_owner(1, created.id)
    assert records is not None
    assert [record["payload"]["summary"] for record in records] == [
        "execution_started",
        "planning_started",
        "runtime_step_not_configured",
    ]
    terminal = records[-1]["payload"]
    assert terminal["status"] == "blocked"
    assert terminal["reason_code"] == "runtime_step_not_configured"
    assert terminal["next_action"] == "configure_bounded_runtime_worker"


def test_local_runtime_rejects_owner_mismatch_without_records(tmp_path) -> None:
    repository = SQLiteMissionRepository(tmp_path / "missions.sqlite3")
    created = repository.create(1, request())
    started = start_mission_execution(repository, owner_id=1, mission=created)

    outcome = run_cost_free_local_step(
        repository,
        owner_id=2,
        mission=started.mission,
    )

    assert outcome.reason == "mission_owner_mismatch"
    records = repository.records_for_owner(1, created.id)
    assert records is not None
    assert len(records) == 1


def test_local_runtime_requires_running_state(tmp_path) -> None:
    repository = SQLiteMissionRepository(tmp_path / "missions.sqlite3")
    created = repository.create(1, request())

    outcome = run_cost_free_local_step(
        repository,
        owner_id=1,
        mission=created,
    )

    assert outcome.reason == "mission_state_not_running"
    assert repository.records_for_owner(1, created.id) == []
