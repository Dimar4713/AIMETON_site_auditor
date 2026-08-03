import pytest

from app.mission_checkpoint import MissionCheckpoint, checkpoint_digest
from app.mission_checkpoint_store import latest_checkpoint, save_checkpoint
from app.runtime_core.models import TaskCreate
from app.runtime_core.storage import RuntimeStore


def make_task(store: RuntimeStore):
    return store.create_task(
        TaskCreate(
            title="Mission checkpoint persistence",
            actor_ref="actor:test",
            mandate_ref="mandate:test",
            commitment="Persist accepted mission checkpoints",
            completion_criteria=["checkpoint survives reopen"],
            correlation_id="corr-checkpoint-test",
        )
    )


def make_checkpoint(sequence: int = 1, state=None):
    state = state or {"phase": "evidence_fetch", "cursor": sequence}
    return MissionCheckpoint(
        mission_id="mission-1",
        sequence=sequence,
        phase="evidence_fetch",
        state_digest=checkpoint_digest(state),
        document_ids=("doc-1",),
        evidence_ids=("ev-1",),
    )


def test_checkpoint_survives_runtime_store_reopen(tmp_path):
    path = tmp_path / "runtime.sqlite3"
    store = RuntimeStore(path)
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

    reopened = RuntimeStore(path)
    assert latest_checkpoint(reopened, task_id=task.id) == expected


def test_repeating_same_checkpoint_is_idempotent(tmp_path):
    store = RuntimeStore(tmp_path / "runtime.sqlite3")
    task = make_task(store)
    item = make_checkpoint()

    first = save_checkpoint(store, task_id=task.id, checkpoint=item, actor_ref=task.actor_ref, mandate_ref=task.mandate_ref, correlation_id=task.correlation_id)
    second = save_checkpoint(store, task_id=task.id, checkpoint=item, actor_ref=task.actor_ref, mandate_ref=task.mandate_ref, correlation_id=task.correlation_id)

    assert first == second
    checkpoint_events = [r for r in store.records(task.id) if r["record"].get("event_type") == "mission.checkpoint"]
    assert len(checkpoint_events) == 1


def test_conflicting_or_older_checkpoint_is_rejected(tmp_path):
    store = RuntimeStore(tmp_path / "runtime.sqlite3")
    task = make_task(store)
    current = make_checkpoint(sequence=2)
    save_checkpoint(store, task_id=task.id, checkpoint=current, actor_ref=task.actor_ref, mandate_ref=task.mandate_ref, correlation_id=task.correlation_id)

    with pytest.raises(ValueError, match="backwards"):
        save_checkpoint(store, task_id=task.id, checkpoint=make_checkpoint(sequence=1), actor_ref=task.actor_ref, mandate_ref=task.mandate_ref, correlation_id=task.correlation_id)

    conflict = make_checkpoint(sequence=2, state={"phase": "other"})
    with pytest.raises(ValueError, match="conflict"):
        save_checkpoint(store, task_id=task.id, checkpoint=conflict, actor_ref=task.actor_ref, mandate_ref=task.mandate_ref, correlation_id=task.correlation_id)
