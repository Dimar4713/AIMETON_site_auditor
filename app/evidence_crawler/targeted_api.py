from __future__ import annotations

from enum import StrEnum
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.entity_resolution.factory import get_entity_resolver
from app.evidence_crawler.factory import get_evidence_crawler
from app.evidence_crawler.models import (
    BootstrapCrawlPolicy,
    BootstrapCrawlResult,
    IdentitySignalKind,
)
from app.mission_orchestrator import (
    ActionCandidate,
    ActionOutcomeState,
    ActionType,
    NextActionPlan,
    PolicySnapshot,
    QuestionState,
    SufficiencyFeedback,
    get_mission_orchestrator,
)
from app.scraper import FetchError


router = APIRouter(tags=["targeted-crawler"])


class TargetedApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IdentityGuardState(StrEnum):
    ALIGNED = "aligned"
    NOT_OBSERVED = "not_observed"
    CONFLICTING = "conflicting"


class TargetedCrawlRequest(TargetedApiModel):
    identity_result_id: str | None = None
    plan: NextActionPlan | None = None
    policy: BootstrapCrawlPolicy = Field(default_factory=BootstrapCrawlPolicy)


class TargetedCrawlEnvelope(TargetedApiModel):
    identity_result_id: str
    selected_candidate_id: str
    guard_state: IdentityGuardState
    expected_identifiers: dict[str, list[str]]
    observed_identifiers: dict[str, list[str]]
    crawl: BootstrapCrawlResult


def _latest_identity(mission_id: str, result_id: str | None):
    history = get_entity_resolver().history(mission_id)
    result = history.revisions[-1]
    if result_id is not None:
        result = next((item for item in history.revisions if item.id == result_id), None)
        if result is None:
            raise ValueError("identity_result_not_found")
    if result.selected_candidate_id is None:
        raise ValueError("targeted_crawl_requires_selected_identity")
    candidate = next(
        item for item in result.candidates if item.id == result.selected_candidate_id
    )
    if not candidate.accepted_identifier_links:
        raise ValueError("targeted_crawl_requires_verified_identifier_links")
    return result, candidate


def _identifier_map(candidate) -> dict[str, list[str]]:
    values: dict[str, set[str]] = {}
    for item in candidate.identifiers:
        if item.scheme in {"inn", "ogrn", "legal_name"}:
            values.setdefault(item.scheme, set()).add(item.normalized_value)
    return {key: sorted(value) for key, value in sorted(values.items())}


def _observed_map(crawl: BootstrapCrawlResult) -> dict[str, list[str]]:
    values: dict[str, set[str]] = {}
    for signal in crawl.identity_signals:
        if signal.kind not in {
            IdentitySignalKind.INN,
            IdentitySignalKind.OGRN,
            IdentitySignalKind.LEGAL_NAME,
        }:
            continue
        value = signal.value.casefold().strip()
        if signal.kind in {IdentitySignalKind.INN, IdentitySignalKind.OGRN}:
            value = "".join(char for char in value if char.isdigit())
        values.setdefault(signal.kind.value, set()).add(value)
    return {key: sorted(value) for key, value in sorted(values.items())}


def _guard(expected: dict[str, list[str]], observed: dict[str, list[str]]) -> IdentityGuardState:
    strong_observed = False
    for scheme in ("inn", "ogrn"):
        current = set(observed.get(scheme, []))
        if not current:
            continue
        strong_observed = True
        if current.isdisjoint(expected.get(scheme, [])):
            return IdentityGuardState.CONFLICTING
    if strong_observed:
        return IdentityGuardState.ALIGNED
    expected_names = set(expected.get("legal_name", []))
    observed_names = set(observed.get("legal_name", []))
    if expected_names and observed_names and not expected_names.isdisjoint(observed_names):
        return IdentityGuardState.ALIGNED
    return IdentityGuardState.NOT_OBSERVED


def _targeted_plan(mission_id: str) -> NextActionPlan:
    orchestrator = get_mission_orchestrator()
    snapshot = orchestrator.get(mission_id)
    target = str(snapshot.contract.target_url)
    host = (urlsplit(target).hostname or "").lower()
    return orchestrator.plan(
        mission_id,
        deficits=["targeted_company_profile"],
        candidates=[
            ActionCandidate(
                action_type=ActionType.CRAWL_URL,
                target=target,
                deficit_code="targeted_company_profile",
                expected_sufficiency_gain=0.8,
                ai_priority=1.0,
            )
        ],
        policy=PolicySnapshot(
            allowed_hosts=frozenset({host}) if host else frozenset(),
            remaining_actions=max(
                1,
                snapshot.contract.budget.max_actions - len(snapshot.turns),
            ),
        ),
    )


@router.post(
    "/{mission_id}/targeted-crawl",
    response_model=TargetedCrawlEnvelope,
)
async def run_targeted_crawl(mission_id: str, request: TargetedCrawlRequest):
    try:
        identity, candidate = _latest_identity(
            mission_id,
            request.identity_result_id,
        )
        orchestrator = get_mission_orchestrator()
        plan = request.plan or _targeted_plan(mission_id)
        crawl = await get_evidence_crawler().run_mission(
            orchestrator,
            mission_id,
            plan=plan,
            policy=request.policy,
        )
        expected = _identifier_map(candidate)
        observed = _observed_map(crawl)
        guard_state = _guard(expected, observed)
        if guard_state == IdentityGuardState.CONFLICTING:
            crawl.status = "blocked"
            crawl.reason_codes = list(
                dict.fromkeys([*crawl.reason_codes, "target_identity_conflict"])
            )
            crawl.outcome.state = ActionOutcomeState.BLOCKED
            crawl.outcome.reason_codes = list(
                dict.fromkeys([*crawl.outcome.reason_codes, "target_identity_conflict"])
            )
        elif request.plan is None:
            orchestrator.record_turn(
                mission_id,
                plan=plan,
                outcome=crawl.outcome,
                feedback=SufficiencyFeedback(
                    achieved=orchestrator.get(mission_id).achieved_sufficiency,
                    question_states={"identity": QuestionState.VERIFIED},
                    critical_gaps=["company_profile_evidence"],
                ),
            )
        return TargetedCrawlEnvelope(
            identity_result_id=identity.id,
            selected_candidate_id=candidate.id,
            guard_state=guard_state,
            expected_identifiers=expected,
            observed_identifiers=observed,
            crawl=crawl,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="mission_or_identity_not_found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FetchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
