from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.evidence_crawler.targeted_api import TargetedCrawlEnvelope
from app.mission_orchestrator import get_mission_orchestrator
from app.sufficiency_evaluator.models import SufficiencyEvaluation
from app.sufficiency_evaluator.service import evaluate_targeted_crawl


router = APIRouter(prefix="/api/missions", tags=["sufficiency-evaluator"])


class SufficiencyApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SufficiencyEvaluationRequest(SufficiencyApiModel):
    targeted_crawl: TargetedCrawlEnvelope
    protocol_completed_questions: list[str] = Field(default_factory=list)


@router.post(
    "/{mission_id}/evaluate-sufficiency",
    response_model=SufficiencyEvaluation,
)
def evaluate_sufficiency(
    mission_id: str,
    request: SufficiencyEvaluationRequest,
):
    try:
        return evaluate_targeted_crawl(
            get_mission_orchestrator(),
            mission_id,
            request.targeted_crawl,
            protocol_completed_questions=set(request.protocol_completed_questions),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="mission_not_found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
