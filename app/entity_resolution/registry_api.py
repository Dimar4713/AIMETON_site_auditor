from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.entity_resolution.factory import get_entity_resolver
from app.entity_resolution.models import IdentityResolutionResult
from app.entity_resolution.registry import RegistryEvidence
from app.entity_resolution.registry_runtime import (
    HumanReviewDecision,
    HumanReviewDecisionRecord,
    RegistryVerificationEnvelope,
    RegistryVerificationHistory,
    get_registry_verification_coordinator,
)
from app.mission_orchestrator import NextActionPlan, get_mission_orchestrator


router = APIRouter(tags=["registry-verification"])


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegistryVerificationRequest(ApiModel):
    base_result_id: str = Field(min_length=1)
    evidence: list[RegistryEvidence] = Field(min_length=1)
    promotion_plan: NextActionPlan | None = None


class HumanReviewDecisionRequest(ApiModel):
    decision: HumanReviewDecision
    reviewer: str = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=2_000)


def _base_identity(mission_id: str, result_id: str) -> IdentityResolutionResult:
    history = get_entity_resolver().history(mission_id)
    result = next((item for item in history.revisions if item.id == result_id), None)
    if result is None:
        raise ValueError("base identity result is not present in history")
    if history.revisions[-1].id != result_id:
        raise ValueError("registry verification requires the latest identity revision")
    if result.selected_candidate_id is None:
        raise ValueError("base identity result has no selected candidate")
    return result


@router.post(
    "/{mission_id}/verify-registry",
    response_model=RegistryVerificationEnvelope,
)
def verify_registry(mission_id: str, request: RegistryVerificationRequest):
    try:
        base = _base_identity(mission_id, request.base_result_id)
        candidate = next(
            item for item in base.candidates if item.id == base.selected_candidate_id
        )
        coordinator = get_registry_verification_coordinator()
        verification = coordinator.verify(mission_id, candidate, request.evidence)
        promoted = None
        if coordinator.can_promote(verification):
            if request.promotion_plan is None:
                raise ValueError("verified registry evidence requires a promotion plan")
            promoted = get_entity_resolver().promote_identifier_links(
                get_mission_orchestrator(),
                mission_id,
                plan=request.promotion_plan,
                base_result_id=base.id,
                accepted_identifier_ids=verification.accepted_identifier_ids,
                artifact_ids=verification.evidence_ids,
                authority_verified=True,
            )
        elif request.promotion_plan is not None:
            raise ValueError("registry result is not eligible for automatic promotion")
        return RegistryVerificationEnvelope(
            verification=verification,
            promoted_identity=promoted,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="mission_or_identity_not_found") from exc
    except (StopIteration, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/{mission_id}/registry-reviews/{review_id}",
    response_model=HumanReviewDecisionRecord,
)
def decide_registry_review(
    mission_id: str,
    review_id: str,
    request: HumanReviewDecisionRequest,
):
    try:
        return get_registry_verification_coordinator().decide(
            mission_id,
            review_id,
            decision=request.decision,
            reviewer=request.reviewer,
            note=request.note,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="registry_review_not_found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get(
    "/{mission_id}/registry-history",
    response_model=RegistryVerificationHistory,
)
def registry_history(mission_id: str):
    try:
        return get_registry_verification_coordinator().history(mission_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="registry_history_not_found") from exc
