from datetime import datetime, timedelta, timezone

import pytest

from app.agent_activity import ActivityBlocked, ActivityConflict, AgentActivityRepository
from app.temporal_orchestrator import TrustedTime

UTC = timezone.utc
BASE = datetime(2026, 8, 6, 16, 0, tzinfo=UTC)


def trusted(at: datetime = BASE) -> TrustedTime:
    return TrustedTime(
        utc=at,
        source="chrony",
        synced=True,
        quality="trusted",
        offset_ms=0.1,
        stratum=2,
    )


def untrusted(at: datetime = BASE) -> TrustedTime:
    return TrustedTime(
        utc=at,
        source="system_clock",
        synced=False,
        quality="fallback",
        offset_ms=999,
        stratum=16,
    )


def test_append_event_is_restart_safe_and_idempotent(tmp_path) -> None:
    path = tmp_path / "activity.sqlite3"
    first_repo = AgentActivityRepository(path)
    first = first_repo.append_event(
        mission_id="mission-1",
        agent_id="agent-a",
        event_type="step_completed",
        state="running",
        reason="tests_passed",
        payload={"sha": "abc"},
        idempotency_key="event-1",
        now=trusted(),
    )

    second_repo = AgentActivityRepository(path)
    repeated = second_repo.append_event(
        mission_id="mission-1",
        agent_id="agent-a",
        event_type="step_completed",
        state="running",
        reason="tests_passed",
        payload={"sha": "abc"},
        idempotency_key="event-1",
        now=trusted(BASE + timedelta(minutes=5)),
    )

    assert repeated == first
    assert second_repo.list_events("mission-1") == (first,)


def test_idempotency_conflict_fails_closed(tmp_path) -> None:
    repo = AgentActivityRepository(tmp_path / "activity.sqlite3")
    repo.append_event(
        mission_id="mission-1",
        agent_id="agent-a",
        event_type="heartbeat",
        state="running",
        reason="ok",
        payload={},
        idempotency_key="same",
        now=trusted(),
    )

    with pytest.raises(ActivityConflict, match="idempotency_key"):
        repo.append_event(
            mission_id="mission-1",
            agent_id="agent-a",
            event_type="heartbeat",
            state="blocked",
            reason="different",
            payload={},
            idempotency_key="same",
            now=trusted(),
        )


def test_heartbeat_updates_local_liveness_without_github(tmp_path) -> None:
    repo = AgentActivityRepository(tmp_path / "activity.sqlite3")
    first = repo.heartbeat(
        mission_id="mission-1",
        agent_id="agent-a",
        state="running",
        reason="working",
        idempotency_key="hb-1",
        now=trusted(),
    )
    second = repo.heartbeat(
        mission_id="mission-1",
        agent_id="agent-a",
        state="waiting",
        reason="external_dependency",
        idempotency_key="hb-2",
        now=trusted(BASE + timedelta(minutes=2)),
    )

    assert first.sequence == 1
    assert second.sequence == 2
    assert repo.latest_heartbeat("mission-1", "agent-a") == second
    assert len(repo.list_events("mission-1")) == 2


def test_repeated_heartbeat_is_idempotent(tmp_path) -> None:
    repo = AgentActivityRepository(tmp_path / "activity.sqlite3")
    first = repo.heartbeat(
        mission_id="mission-1",
        agent_id="agent-a",
        state="running",
        reason="working",
        idempotency_key="hb-1",
        now=trusted(),
    )
    repeated = repo.heartbeat(
        mission_id="mission-1",
        agent_id="agent-a",
        state="running",
        reason="working",
        idempotency_key="hb-1",
        now=trusted(BASE + timedelta(minutes=1)),
    )

    assert repeated == first
    assert repeated.sequence == 1
    assert len(repo.list_events("mission-1")) == 1


def test_untrusted_time_blocks_before_mutation(tmp_path) -> None:
    repo = AgentActivityRepository(tmp_path / "activity.sqlite3")

    with pytest.raises(ActivityBlocked, match="blocked:untrusted_time"):
        repo.heartbeat(
            mission_id="mission-1",
            agent_id="agent-a",
            state="running",
            reason="working",
            idempotency_key="hb-1",
            now=untrusted(),
        )

    assert repo.latest_heartbeat("mission-1", "agent-a") is None
    assert repo.list_events("mission-1") == ()
