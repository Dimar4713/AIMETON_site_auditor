from __future__ import annotations

from typing import Any, Protocol

import httpx

from app.external_sources import run_enriched_site_analysis
from app.mission_contract import Mission, MissionState, utc_now
from app.scraper import FetchError, fetch_site


class BoundedRuntimeRepository(Protocol):
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


def _turn(
    repository: BoundedRuntimeRepository,
    mission_id: str,
    *,
    summary: str,
    status: str,
    source_count: int = 0,
    reason_code: str | None = None,
    next_action: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "turn_id": f"{summary}:{mission_id}",
        "status": status,
        "summary": summary,
        "source_count": source_count,
    }
    if status in {"completed", "blocked", "degraded"}:
        payload["completed_at"] = utc_now().isoformat()
    if reason_code:
        payload["reason_code"] = reason_code
    if next_action:
        payload["next_action"] = next_action
    repository.append_record(mission_id, "turn", payload)


async def run_owned_site_analysis(
    repository: BoundedRuntimeRepository,
    *,
    owner_id: int,
    mission: Mission,
) -> None:
    """Execute one bounded owner-scoped site-analysis mission.

    The worker reuses the existing fetch/enrichment pipeline while keeping the
    canonical user mission and its report inside owner-scoped persistence.
    Secrets and provider payloads are not copied into the user event stream.
    """
    if mission.owner_id != owner_id or mission.state is not MissionState.RUNNING:
        return

    try:
        _turn(
            repository,
            mission.id,
            summary="planning_started",
            status="running",
        )
        _turn(
            repository,
            mission.id,
            summary="site_fetch_started",
            status="running",
        )
        page = await fetch_site(mission.target_ref)
        _turn(
            repository,
            mission.id,
            summary="site_fetch_completed",
            status="running",
        )

        result = await run_enriched_site_analysis(
            page["final_url"],
            page["title"],
            page["text"],
        )
        report_payload = result.model_copy(
            update={"mission_id": mission.id}
        ).model_dump(mode="json")
        repository.append_record(
            mission.id,
            "report_payload",
            report_payload,
        )
        repository.append_record(
            mission.id,
            "report_metadata",
            {
                "report_id": f"report:{mission.id}",
                "status": "completed",
                "format": "json",
                "content_type": "application/json",
                "available": True,
                "release_level": "preliminary",
                "blocked_reason": None,
                "created_at": utc_now().isoformat(),
            },
        )
        _turn(
            repository,
            mission.id,
            summary="analysis_completed",
            status="completed",
            source_count=len(result.sources),
        )
        repository.update_state_for_owner(
            owner_id,
            mission.id,
            MissionState.COMPLETED,
        )
    except (FetchError, httpx.HTTPError, ValueError):
        _turn(
            repository,
            mission.id,
            summary="analysis_failed",
            status="blocked",
            reason_code="site_analysis_failed",
            next_action="verify_target_and_retry",
        )
        repository.update_state_for_owner(
            owner_id,
            mission.id,
            MissionState.BLOCKED,
        )
    except Exception:
        _turn(
            repository,
            mission.id,
            summary="analysis_failed",
            status="blocked",
            reason_code="bounded_runtime_failed",
            next_action="inspect_runtime_trace",
        )
        repository.update_state_for_owner(
            owner_id,
            mission.id,
            MissionState.BLOCKED,
        )
