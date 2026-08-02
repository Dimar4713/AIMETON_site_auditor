from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.mission_contract import Mission, MissionState


class ExecutionMissionRepository(Protocol):
    def append_record(
        self,
        mission_id: str,
        kind: str,
        payload: dict[str, Any],
        *,
        digest: str | None = None,
        record_id: str | None = None,
    ) -> str: ...

    def update_state_for_owner(
        self,
        owner_id: int,
        mission_id: str,
        state: MissionState,
    ) -> Mission | None: ...


@dataclass(frozen=True)
class MissionExecutionStart:
    mission: Mission
    event_id: str | None
    started: bool
    reason: str


def start_mission_execution(
    repository: ExecutionMissionRepository,
    *,
    owner_id: int,
    mission: Mission,
) -> MissionExecutionStart:
    """Persist start evidence before exposing a mission as running.

    This function does not call providers or LLMs. It establishes the truthful
    execution boundary used by the later bounded runtime worker.
    """
    if mission.owner_id != owner_id:
        return MissionExecutionStart(
            mission=mission,
            event_id=None,
            started=False,
            reason="mission_owner_mismatch",
        )
    if mission.state is not MissionState.CREATED:
        return MissionExecutionStart(
            mission=mission,
            event_id=None,
            started=False,
            reason="mission_state_not_created",
        )

    try:
        event_id = repository.append_record(
            mission.id,
            "turn",
            {
                "turn_id": f"execution-start:{mission.id}",
                "status": "running",
                "summary": "execution_started",
                "source_count": 0,
            },
        )
        running = repository.update_state_for_owner(
            owner_id,
            mission.id,
            MissionState.RUNNING,
        )
    except Exception:
        blocked = repository.update_state_for_owner(
            owner_id,
            mission.id,
            MissionState.BLOCKED,
        )
        return MissionExecutionStart(
            mission=blocked or mission,
            event_id=None,
            started=False,
            reason="execution_start_persistence_failed",
        )

    if running is None:
        return MissionExecutionStart(
            mission=mission,
            event_id=event_id,
            started=False,
            reason="mission_state_transition_failed",
        )
    return MissionExecutionStart(
        mission=running,
        event_id=event_id,
        started=True,
        reason="execution_started",
    )
