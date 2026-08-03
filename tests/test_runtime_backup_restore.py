import sqlite3

import pytest

from app.mission_checkpoint import MissionCheckpoint, checkpoint_digest
from app.mission_checkpoint_store import latest_checkpoint, save_checkpoint
from app.runtime_core.backup import backup_runtime_database, restore_runtime_database
from app.runtime_core.models import TaskCreate
from app.runtime_core.storage import RuntimeStore


def make_task(store: RuntimeStore):
    return store.create_task(
        TaskCreate(
            title="Runtime backup restore",
            actor_ref="actor:test",
            mandate_ref="mandate:test",
            commitment="Restore mission checkpoint",
            completion_criteria=["checkpoint survives restore"],
            correlation_id="corr-backup-restore-test",
        )
    )


def make_checkpoint():
    return MissionCheckpoint(
        mission_id="mission-backup-1",
        sequence=3,
        phase="evidence_fetch",
        state_digest=checkpoint_digest({"phase": "evidence_fetch", "cursor": 3}),
        document_ids=("doc-1", "doc-2"),
        evidence_ids=("ev-1",),
    )


def test_backup_restore_preserves_latest_checkpoint(tmp_path):
    live_path = tmp_path / "runtime.sqlite3"
    backup_path = tmp_path / "backup" / "runtime.sqlite3.bak"
    restored_path = tmp_path / "restore" / "runtime.sqlite3"

    store = RuntimeStore(live_path)
    task = make_task(store)
    expected = make_checkpoint()
    save_checkpoint(
        store,
        task_id=task.id,
        checkpoint=expected,
        actor_ref=task.actor_ref,
        mandate_ref=task.mandate_ref,
        correlation_id=task.correlation_id,
    )

    backup_runtime_database(live_path, backup_path)
    restore_runtime_database(backup_path, restored_path)

    restored = RuntimeStore(restored_path)
    assert latest_checkpoint(restored, task_id=task.id) == expected
    assert backup_path.exists()


def test_corrupt_backup_is_rejected_without_replacing_destination(tmp_path):
    corrupt = tmp_path / "corrupt.sqlite3"
    corrupt.write_bytes(b"not a sqlite database")
    destination = tmp_path / "runtime.sqlite3"
    destination.write_bytes(b"keep-me")

    with pytest.raises((sqlite3.DatabaseError, ValueError)):
        restore_runtime_database(corrupt, destination)

    assert destination.read_bytes() == b"keep-me"


def test_backup_replaces_destination_only_after_integrity_check(tmp_path):
    source_path = tmp_path / "source.sqlite3"
    destination_path = tmp_path / "backup.sqlite3"
    store = RuntimeStore(source_path)
    task = make_task(store)

    backup_runtime_database(source_path, destination_path)

    with sqlite3.connect(destination_path) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT COUNT(*) FROM runtime_tasks").fetchone()[0] == 1
    assert task.id
