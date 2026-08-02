from __future__ import annotations

import sqlite3

import pytest

from app.mission_contract import MissionCreate, MissionState
from app.mission_sqlite import MISSION_SCHEMA_VERSION, SQLiteMissionRepository


def request(title: str = "Audit company") -> MissionCreate:
    return MissionCreate(
        title=title,
        target_ref="https://example.test",
        input_snapshot={"source": "test"},
        correlation_id="corr-test",
    )


def test_migration_is_idempotent_and_versioned(tmp_path) -> None:
    path = tmp_path / "missions.sqlite3"

    repository = SQLiteMissionRepository(path)
    repository.migrate()
    repository.migrate()

    with sqlite3.connect(path) as connection:
        version = connection.execute(
            "SELECT value FROM mission_meta WHERE key = 'schema_version'"
        ).fetchone()[0]
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert version == str(MISSION_SCHEMA_VERSION)
    assert {"mission_meta", "missions", "mission_records"} <= tables


def test_mission_survives_repository_reopen(tmp_path) -> None:
    path = tmp_path / "missions.sqlite3"
    first = SQLiteMissionRepository(path)
    mission = first.create(101, request())
    record_id = first.append_record(
        mission.id,
        "sufficiency",
        {"level": "L4", "verdict": "sufficient"},
        digest="sha256:test",
    )

    second = SQLiteMissionRepository(path)
    restored = second.get_for_owner(101, mission.id)
    records = second.records_for_owner(101, mission.id)

    assert restored is not None
    assert restored.owner_id == 101
    assert restored.state is MissionState.CREATED
    assert records is not None
    assert records[0]["id"] == record_id
    assert records[0]["kind"] == "sufficiency"
    assert records[0]["digest"] == "sha256:test"


def test_owner_queries_and_mutations_fail_closed(tmp_path) -> None:
    repository = SQLiteMissionRepository(tmp_path / "missions.sqlite3")
    mission_a = repository.create(1, request("A"))
    mission_b = repository.create(2, request("B"))

    assert repository.get_for_owner(2, mission_a.id) is None
    assert repository.update_state_for_owner(2, mission_a.id, MissionState.COMPLETED) is None
    assert repository.records_for_owner(2, mission_a.id) is None
    assert [mission.id for mission in repository.list_for_owner(1)] == [mission_a.id]
    assert [mission.id for mission in repository.list_for_owner(2)] == [mission_b.id]

    unchanged = repository.get_for_owner(1, mission_a.id)
    assert unchanged is not None
    assert unchanged.state is MissionState.CREATED


def test_owner_state_update_persists_and_preserves_typed_state(tmp_path) -> None:
    path = tmp_path / "missions.sqlite3"
    repository = SQLiteMissionRepository(path)
    mission = repository.create(8, request())

    updated = repository.update_state_for_owner(8, mission.id, MissionState.DEGRADED)

    assert updated is not None
    assert updated.state is MissionState.DEGRADED
    reopened = SQLiteMissionRepository(path)
    restored = reopened.get_for_owner(8, mission.id)
    assert restored is not None
    assert restored.state is MissionState.DEGRADED


def test_records_have_stable_identifiers_and_supported_kinds(tmp_path) -> None:
    repository = SQLiteMissionRepository(tmp_path / "missions.sqlite3")
    mission = repository.create(9, request())

    stable_id = repository.append_record(
        mission.id,
        "turn",
        {"ordinal": 1, "summary": "first turn"},
        record_id="turn-stable-1",
    )
    repository.append_record(
        mission.id,
        "report_metadata",
        {"report_id": "report-1", "status": "blocked"},
    )

    records = repository.records_for_owner(9, mission.id)
    assert records is not None
    assert stable_id == "turn-stable-1"
    assert [record["kind"] for record in records] == ["turn", "report_metadata"]

    with pytest.raises(ValueError):
        repository.append_record(mission.id, "secret_trace", {"token": "must-not-store"})


def test_append_record_requires_existing_mission(tmp_path) -> None:
    repository = SQLiteMissionRepository(tmp_path / "missions.sqlite3")

    with pytest.raises(KeyError):
        repository.append_record("mission-missing", "turn", {"ordinal": 1})
