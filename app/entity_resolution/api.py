from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.entity_resolution.dadata_api import router as dadata_router
from app.entity_resolution.factory import get_entity_resolver
from app.entity_resolution.models import (
    IdentityResolutionHistory,
    IdentityResolutionResult,
)
from app.entity_resolution.registry_api import router as registry_router
from app.evidence_crawler.models import BootstrapCrawlResult, IdentitySignalKind
from app.mission_orchestrator import (
    ActionCandidate,
    ActionType,
    NextActionPlan,
    PolicySnapshot,
    QuestionState,
    SufficiencyFeedback,
    SufficiencyLevel,
    get_mission_orchestrator,
)
from app.search_providers.yandex_api import router as yandex_search_router


router = APIRouter(prefix="/api/missions", tags=["entity-resolution"])
router.include_router(registry_router)
router.include_router(dadata_router)
router.include_router(yandex_search_router)


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IdentityResolutionRequest(ApiModel):
    plan: NextActionPlan | None = None
    bootstrap_results: list[BootstrapCrawlResult] = Field(min_length=1)


def _bootstrap_feedback(batch: BootstrapCrawlResult) -> SufficiencyFeedback:
    kinds = {signal.kind for signal in batch.identity_signals}
    question_states: dict[str, QuestionState] = {}
    critical_gaps: list[str] = []

    if kinds & {
        IdentitySignalKind.INN,
        IdentitySignalKind.OGRN,
        IdentitySignalKind.LEGAL_NAME,
    }:
        question_states["identity"] = QuestionState.PARTIALLY_VERIFIED
    else:
        question_states["identity"] = QuestionState.NOT_SEARCHED
        critical_gaps.append("identity")

    if kinds & {
        IdentitySignalKind.EMAIL,
        IdentitySignalKind.PHONE,
        IdentitySignalKind.ADDRESS,
    }:
        question_states["contacts"] = QuestionState.PARTIALLY_VERIFIED

    if "identity" not in critical_gaps:
        critical_gaps.append("identity_link_evidence")

    return SufficiencyFeedback(
        achieved=(
            SufficiencyLevel.L1
            if batch.pages or batch.identity_signals
            else SufficiencyLevel.L0
        ),
        question_states=question_states,
        critical_gaps=critical_gaps,
    )


def _auto_resolution_plan(
    mission_id: str,
    batches: list[BootstrapCrawlResult],
) -> NextActionPlan:
    orchestrator = get_mission_orchestrator()
    snapshot = orchestrator.get(mission_id)

    for batch in batches:
        if batch.mission_id != mission_id:
            raise ValueError("bootstrap result belongs to another mission")
        if batch.analysis_id != snapshot.contract.analysis_id:
            raise ValueError("bootstrap result breaks analysis_id")
        if batch.correlation_id != snapshot.contract.correlation_id:
            raise ValueError("bootstrap result breaks correlation_id")

    latest = batches[-1]
    if len(snapshot.turns) < latest.plan.turn_number:
        snapshot = orchestrator.record_turn(
            mission_id,
            plan=latest.plan,
            outcome=latest.outcome,
            feedback=_bootstrap_feedback(latest),
        )
    elif len(snapshot.turns) > latest.plan.turn_number:
        raise ValueError("bootstrap result is older than current mission state")

    host = (urlsplit(str(snapshot.contract.target_url)).hostname or "").lower()
    return orchestrator.plan(
        mission_id,
        deficits=["identity"],
        candidates=[
            ActionCandidate(
                action_type=ActionType.RESOLVE_IDENTITY,
                target=mission_id,
                deficit_code="identity",
                expected_sufficiency_gain=0.7,
                ai_priority=0.9,
            )
        ],
        policy=PolicySnapshot(
            allowed_hosts=frozenset({host}) if host else frozenset(),
            remaining_actions=max(
                0,
                snapshot.contract.budget.max_actions - len(snapshot.turns),
            ),
        ),
    )


@router.post(
    "/{mission_id}/resolve-identity",
    response_model=IdentityResolutionResult,
)
def resolve_identity(
    mission_id: str,
    request: IdentityResolutionRequest,
):
    try:
        orchestrator = get_mission_orchestrator()
        plan = request.plan or _auto_resolution_plan(
            mission_id,
            request.bootstrap_results,
        )
        result = get_entity_resolver().resolve(
            orchestrator,
            mission_id,
            plan=plan,
            bootstrap_results=request.bootstrap_results,
        )
        if request.plan is None:
            orchestrator.record_turn(
                mission_id,
                plan=plan,
                outcome=result.outcome,
                feedback=result.recommended_feedback,
            )
        return result
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="mission_not_found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get(
    "/{mission_id}/identity-history",
    response_model=IdentityResolutionHistory,
)
def identity_history(mission_id: str):
    try:
        return get_entity_resolver().history(mission_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail="identity_history_not_found",
        ) from exc
