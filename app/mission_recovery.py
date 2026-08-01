from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel

from app.mission_contract import Mission, MissionState


class ResumeDisposition(StrEnum):
    RESUME = "resume"
    REVIEW_DEGRADED = "review_degraded"
    REMAIN_BLOCKED = "remain_blocked"
    TERMINAL = "terminal"


# Backward-compatible alias for existing acceptance tooling. New code should use
# ResumeDisposition as the canonical public name.
RecoveryDisposition = ResumeDisposition


class MissionRecoveryDecision(BaseModel):
    mission_id: str
    state: MissionState
    disposition: ResumeDisposition
    resumable: bool
    reason: str


def recovery_decision(mission: Mission) -> MissionRecoveryDecision:
    """Return a deterministic recovery decision without rewriting mission truth.

    Recovery never promotes degraded or blocked work to completed. The caller may
    resume running work, but terminal and exceptional states remain explicit.
    """

    if mission.state is MissionState.RUNNING:
        return MissionRecoveryDecision(
            mission_id=mission.id,
            state=mission.state,
            disposition=ResumeDisposition.RESUME,
            resumable=True,
            reason="mission_running_resume_from_persistent_snapshot",
        )
    if mission.state is MissionState.DEGRADED:
        return MissionRecoveryDecision(
            mission_id=mission.id,
            state=mission.state,
            disposition=ResumeDisposition.REVIEW_DEGRADED,
            resumable=False,
            reason="mission_degraded_requires_explicit_review",
        )
    if mission.state is MissionState.BLOCKED:
        return MissionRecoveryDecision(
            mission_id=mission.id,
            state=mission.state,
            disposition=ResumeDisposition.REMAIN_BLOCKED,
            resumable=False,
            reason="mission_blocked_requires_blocker_resolution",
        )
    return MissionRecoveryDecision(
        mission_id=mission.id,
        state=mission.state,
        disposition=ResumeDisposition.TERMINAL,
        resumable=False,
        reason="mission_completed_is_terminal",
    )
