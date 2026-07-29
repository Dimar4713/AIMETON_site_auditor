from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.evidence_crawler.factory import get_evidence_crawler
from app.evidence_crawler.models import (
    BootstrapCrawlPolicy,
    BootstrapCrawlResult,
)
from app.mission_orchestrator import (
    NextActionPlan,
    get_mission_orchestrator,
)
from app.scraper import FetchError


router = APIRouter(prefix="/api/missions", tags=["evidence-crawler"])


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BootstrapRunRequest(ApiModel):
    plan: NextActionPlan
    policy: BootstrapCrawlPolicy = Field(default_factory=BootstrapCrawlPolicy)


@router.post(
    "/{mission_id}/bootstrap-crawl",
    response_model=BootstrapCrawlResult,
)
async def run_bootstrap_crawl(
    mission_id: str,
    request: BootstrapRunRequest,
):
    try:
        return await get_evidence_crawler().run_mission(
            get_mission_orchestrator(),
            mission_id,
            plan=request.plan,
            policy=request.policy,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="mission_not_found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FetchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
