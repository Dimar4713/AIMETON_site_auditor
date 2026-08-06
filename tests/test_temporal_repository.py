from datetime import datetime, timedelta, timezone

import pytest

from app.temporal_orchestrator import TemporalIntent
from app.temporal_repository import IdempotencyConflict, TemporalIntentRepository, VersionConflict


def _intent(wait_id: str = "wait-1") -> TemporalIntent:
    created = datetime(2026, 8, 6, 13, 0, tzinfo=timezone.utc)
    return TemporalIntent(
        wait_id=wait_id,
        mission_id="mission-1",
        created_at=created,
        resume_not_before=created + timedelta(minutes=5),
        deadline=created + timedelta(minutes=30),
    )


def test_repeated_create_is_idempotent(tmp_path):
    repo = TemporalIntentRepository(tmp_path / "temporal.sqlite3")
    first = repo.create(_intent(), idempotency_key="same")
    second = repo.create(_intent(), idempotency_key="same")
    assert second == first


def test_conflicting_payload_fails_closed(tmp_path):
    repo = TemporalIntentRepository(tmp_path / "temporal.sqlite3")
    repo.create(_intent("wait-1"), idempotency_key="same")
    with pytest.raises(IdempotencyConflict):
        repo.create(_intent("wait-2"), idempotency_key="same")


def test_restart_preserves_intent(tmp_path):
    path = tmp_path / "temporal.sqlite3"
    TemporalIntentRepository(path).create(_intent(), idempotency_key="key")
    assert TemporalIntentRepository(path).get("wait-1") == _intent()


def test_optimistic_versioning_rejects_stale_update(tmp_path):
    repo = TemporalIntentRepository(tmp_path / "temporal.sqlite3")
    repo.create(_intent(), idempotency_key="key")
    assert repo.update_status("wait-1", status="waiting", expected_version=1) == 2
    with pytest.raises(VersionConflict):
        repo.update_status("wait-1", status="ready", expected_version=1)
