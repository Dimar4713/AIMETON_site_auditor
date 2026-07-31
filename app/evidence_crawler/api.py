from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.evidence_crawler.factory import get_evidence_crawler
from app.evidence_crawler.models import (
    BootstrapCrawlPolicy,
    BootstrapCrawlResult,
)
from app.evidence_crawler.targeted_api import router as targeted_router
from app.mission_orchestrator import (
    ActionCandidate,
    ActionType,
    NextActionPlan,
    PolicySnapshot,
    QuestionState,
    get_mission_orchestrator,
)
from app.scraper import FetchError


router = APIRouter(prefix="/api/missions", tags=["evidence-crawler"])
router.include_router(targeted_router)


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BootstrapRunRequest(ApiModel):
    plan: NextActionPlan | None = None
    policy: BootstrapCrawlPolicy = Field(default_factory=BootstrapCrawlPolicy)


def _bootstrap_plan(mission_id: str) -> NextActionPlan:
    orchestrator = get_mission_orchestrator()
    snapshot = orchestrator.get(mission_id)
    target_url = str(snapshot.contract.target_url)
    host = (urlsplit(target_url).hostname or "").lower()
    if not host:
        raise ValueError("mission_target_host_missing")

    deficits = sorted(
        code
        for code, state in snapshot.question_states.items()
        if state in {
            QuestionState.NOT_SEARCHED,
            QuestionState.PARTIALLY_VERIFIED,
            QuestionState.CONFLICTING,
            QuestionState.BLOCKED,
            QuestionState.DEGRADED,
        }
    )
    if not deficits:
        deficits = ["bootstrap"]

    return orchestrator.plan(
        mission_id,
        deficits=deficits,
        candidates=[
            ActionCandidate(
                action_type=ActionType.CRAWL_URL,
                target=target_url,
                deficit_code="bootstrap",
                expected_sufficiency_gain=0.4,
                ai_priority=1.0,
            )
        ],
        policy=PolicySnapshot(
            allowed_hosts=frozenset({host}),
            remaining_actions=max(1, snapshot.contract.budget.max_actions - len(snapshot.turns)),
        ),
    )


@router.post(
    "/{mission_id}/bootstrap-crawl",
    response_model=BootstrapCrawlResult,
)
async def run_bootstrap_crawl(
    mission_id: str,
    request: BootstrapRunRequest,
):
    try:
        orchestrator = get_mission_orchestrator()
        plan = request.plan or _bootstrap_plan(mission_id)
        return await get_evidence_crawler().run_mission(
            orchestrator,
            mission_id,
            plan=plan,
            policy=request.policy,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="mission_not_found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FetchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
