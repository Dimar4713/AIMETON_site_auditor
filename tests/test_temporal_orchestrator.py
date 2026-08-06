from datetime import datetime, timezone

import pytest

from app.temporal_orchestrator import (
    TemporalIntent,
    TemporalState,
    TrustedTime,
    evaluate_temporal_intent,
)


def utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def trusted(value: str) -> TrustedTime:
    return TrustedTime(
        utc=utc(value),
        source="chrony",
        synced=True,
        quality="trusted",
        offset_ms=0.01,
        stratum=2,
    )


def intent() -> TemporalIntent:
    return TemporalIntent(
        wait_id="wait-1",
        mission_id="mission-1",
        created_at=utc("2026-08-06T13:00:00Z"),
        resume_not_before=utc("2026-08-06T13:10:00Z"),
        deadline=utc("2026-08-06T13:30:00Z"),
        fallback_interval_seconds=300,
    )


def test_waiting_before_resume_time() -> None:
    decision = evaluate_temporal_intent(intent(), trusted("2026-08-06T13:05:00Z"))
    assert decision.state is TemporalState.WAITING
    assert decision.next_check_at == utc("2026-08-06T13:10:00Z")


def test_ready_after_resume_before_deadline() -> None:
    decision = evaluate_temporal_intent(intent(), trusted("2026-08-06T13:10:00Z"))
    assert decision.state is TemporalState.READY
    assert decision.next_check_at is None


def test_deadline_has_priority() -> None:
    decision = evaluate_temporal_intent(intent(), trusted("2026-08-06T13:30:00Z"))
    assert decision.state is TemporalState.TIMED_OUT
    assert decision.reason == "deadline_reached:escalate"


def test_untrusted_time_blocks_decision() -> None:
    now = TrustedTime(
        utc=utc("2026-08-06T13:05:00Z"),
        source="system",
        synced=False,
        quality="degraded",
        offset_ms=100,
        stratum=16,
    )
    decision = evaluate_temporal_intent(intent(), now)
    assert decision.state is TemporalState.BLOCKED
    assert decision.reason == "blocked:untrusted_time"


def test_deadline_before_resume_is_invalid() -> None:
    with pytest.raises(ValueError, match="deadline"):
        TemporalIntent(
            wait_id="wait-1",
            mission_id="mission-1",
            created_at=utc("2026-08-06T13:00:00Z"),
            resume_not_before=utc("2026-08-06T13:30:00Z"),
            deadline=utc("2026-08-06T13:10:00Z"),
        )


def test_non_utc_timestamp_is_invalid() -> None:
    with pytest.raises(ValueError, match="UTC"):
        TemporalIntent(
            wait_id="wait-1",
            mission_id="mission-1",
            created_at=datetime(2026, 8, 6, 13, 0),
            resume_not_before=utc("2026-08-06T13:10:00Z"),
            deadline=utc("2026-08-06T13:30:00Z"),
        )
