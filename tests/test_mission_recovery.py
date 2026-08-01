import pytest

from app.mission_contract import Mission, MissionState
from app.mission_recovery import ResumeDisposition, recovery_decision


def mission(state: MissionState) -> Mission:
    return Mission(
        owner_id=7,
        title="Persistent audit",
        target_ref="https://example.org",
        state=state,
        correlation_id="corr-recovery-1",
    )


@pytest.mark.parametrize(
    ("state", "disposition", "resumable"),
    [
        (MissionState.RUNNING, ResumeDisposition.RESUME, True),
        (MissionState.DEGRADED, ResumeDisposition.REVIEW_DEGRADED, False),
        (MissionState.BLOCKED, ResumeDisposition.REMAIN_BLOCKED, False),
        (MissionState.COMPLETED, ResumeDisposition.TERMINAL, False),
    ],
)
def test_recovery_is_deterministic_and_preserves_truth(state, disposition, resumable):
    stored = mission(state)

    first = recovery_decision(stored)
    second = recovery_decision(stored)

    assert first == second
    assert first.state is state
    assert first.disposition is disposition
    assert first.resumable is resumable
    assert stored.state is state


def test_degraded_and_blocked_are_never_promoted_to_completed():
    for state in (MissionState.DEGRADED, MissionState.BLOCKED):
        decision = recovery_decision(mission(state))
        assert decision.state is state
        assert decision.disposition is not ResumeDisposition.TERMINAL
        assert "completed" not in decision.reason
