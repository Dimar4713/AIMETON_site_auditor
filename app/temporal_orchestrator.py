from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum


class TemporalState(StrEnum):
    SCHEDULED = "scheduled"
    WAITING = "waiting"
    READY = "ready"
    TIMED_OUT = "timed_out"
    BLOCKED = "blocked"


class TimeoutAction(StrEnum):
    ESCALATE = "escalate"
    CANCEL = "cancel"
    FALLBACK = "fallback"


@dataclass(frozen=True, slots=True)
class TrustedTime:
    utc: datetime
    source: str
    synced: bool
    quality: str
    offset_ms: float
    stratum: int

    def __post_init__(self) -> None:
        _require_utc(self.utc, "utc")

    @property
    def trusted(self) -> bool:
        return (
            self.source == "chrony"
            and self.synced
            and self.quality == "trusted"
            and abs(self.offset_ms) <= 50
            and self.stratum <= 4
        )


@dataclass(frozen=True, slots=True)
class TemporalIntent:
    wait_id: str
    mission_id: str
    created_at: datetime
    resume_not_before: datetime
    deadline: datetime
    wake_condition: str | None = None
    fallback_interval_seconds: int = 300
    timeout_action: TimeoutAction = TimeoutAction.ESCALATE
    version: int = 1

    def __post_init__(self) -> None:
        for name in ("wait_id", "mission_id"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")
        for name in ("created_at", "resume_not_before", "deadline"):
            _require_utc(getattr(self, name), name)
        if self.deadline < self.resume_not_before:
            raise ValueError("deadline must not be earlier than resume_not_before")
        if self.created_at > self.deadline:
            raise ValueError("created_at must not be later than deadline")
        if self.fallback_interval_seconds <= 0:
            raise ValueError("fallback_interval_seconds must be positive")
        if self.version < 1:
            raise ValueError("version must be at least 1")


@dataclass(frozen=True, slots=True)
class TemporalDecision:
    state: TemporalState
    evaluated_at: datetime
    reason: str
    next_check_at: datetime | None


def evaluate_temporal_intent(intent: TemporalIntent, now: TrustedTime) -> TemporalDecision:
    """Evaluate temporal state without reading local clocks or causing side effects."""
    if not now.trusted:
        return TemporalDecision(
            state=TemporalState.BLOCKED,
            evaluated_at=now.utc,
            reason="blocked:untrusted_time",
            next_check_at=None,
        )
    if now.utc >= intent.deadline:
        return TemporalDecision(
            state=TemporalState.TIMED_OUT,
            evaluated_at=now.utc,
            reason=f"deadline_reached:{intent.timeout_action.value}",
            next_check_at=None,
        )
    if now.utc >= intent.resume_not_before:
        return TemporalDecision(
            state=TemporalState.READY,
            evaluated_at=now.utc,
            reason="resume_not_before_reached",
            next_check_at=None,
        )
    fallback = now.utc.timestamp() + intent.fallback_interval_seconds
    next_check = datetime.fromtimestamp(
        min(fallback, intent.resume_not_before.timestamp(), intent.deadline.timestamp()),
        tz=timezone.utc,
    )
    return TemporalDecision(
        state=TemporalState.WAITING,
        evaluated_at=now.utc,
        reason="waiting_for_time_or_wake_condition",
        next_check_at=next_check,
    )


def _require_utc(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware UTC")
    if value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError(f"{name} must use UTC")
