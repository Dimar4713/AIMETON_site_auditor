from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.mission_contract import Mission, MissionState


class LocalRuntimeRepository(Protocol):
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
class LocalRuntimeOutcome:
    mission: Mission
    planning_event_id: str | None
    terminal_event_id: str | None
    reason: str


def run_cost_free_local_step(
    repository: LocalRuntimeRepository,
    *,
    owner_id: int,
    mission: Mission,
) -> LocalRuntimeOutcome:
    """Run one deterministic local step and terminate truthfully.

    No crawler, network provider, AI/LLM or paid service is invoked. Until a
    real bounded worker is configured, the mission becomes typed ``blocked``
    instead of remaining indefinitely ``running``.
    """
    if mission.owner_id != owner_id:
        return LocalRuntimeOutcome(mission, None, None, "mission_owner_mismatch")
    if mission.state is not MissionState.RUNNING:
        return LocalRuntimeOutcome(mission, None, None, "mission_state_not_running")

    try:
        planning_event_id = repository.append_record(
            mission.id,
            "turn",
            {
                "turn_id": f"planning-start:{mission.id}",
                "status": "running",
                "summary": "planning_started",
                "source_count": 0,
            },
        )
        terminal_event_id = repository.append_record(
            mission.id,
            "turn",
            {
                "turn_id": f"runtime-blocked:{mission.id}",
                "status": "blocked",
                "summary": "runtime_step_not_configured",
                "source_count": 0,
                "reason_code": "runtime_step_not_configured",
                "next_action": "configure_bounded_runtime_worker",
            },
        )
        blocked = repository.update_state_for_owner(
            owner_id,
            mission.id,
            MissionState.BLOCKED,
        )
    except Exception:
        blocked = repository.update_state_for_owner(
            owner_id,
            mission.id,
            MissionState.BLOCKED,
        )
        return LocalRuntimeOutcome(
            blocked or mission,
            None,
            None,
            "local_runtime_persistence_failed",
        )

    return LocalRuntimeOutcome(
        blocked or mission,
        planning_event_id,
        terminal_event_id,
        "runtime_step_not_configured",
    )
