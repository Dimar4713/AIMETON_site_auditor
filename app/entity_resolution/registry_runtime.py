from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from enum import StrEnum
from threading import RLock

from pydantic import BaseModel, ConfigDict, Field

from app.entity_resolution.models import IdentityResolutionResult
from app.entity_resolution.registry import (
    HumanReviewRequest,
    OfficialRegistryVerifier,
    RegistryEvidence,
    RegistryVerificationResult,
    RegistryVerificationState,
)
from app.sef.models import Identifier


class RegistryRuntimeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HumanReviewDecision(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"
    REQUEST_MORE_EVIDENCE = "request_more_evidence"


class HumanReviewDecisionRecord(RegistryRuntimeModel):
    review_id: Identifier
    candidate_id: Identifier
    decision: HumanReviewDecision
    decided_at: datetime
    reviewer: str = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=2_000)


class RegistryVerificationEnvelope(RegistryRuntimeModel):
    verification: RegistryVerificationResult
    promoted_identity: IdentityResolutionResult | None = None


class RegistryVerificationHistory(RegistryRuntimeModel):
    mission_id: Identifier
    results: list[RegistryVerificationResult] = Field(default_factory=list)
    decisions: list[HumanReviewDecisionRecord] = Field(default_factory=list)


class RegistryVerificationCoordinator:
    """Process-local authority gate and append-only review ledger.

    Official document acquisition remains outside this class. Only locator-bound
    RegistryEvidence may enter the verifier. Human review never overrides an
    authoritative INN/OGRN mismatch; it can only accept relationship scope,
    reject the candidate, or request more evidence.
    """

    def __init__(self) -> None:
        self._verifier = OfficialRegistryVerifier()
        self._results: dict[str, list[RegistryVerificationResult]] = {}
        self._reviews: dict[str, HumanReviewRequest] = {}
        self._review_mission: dict[str, str] = {}
        self._decisions: dict[str, HumanReviewDecisionRecord] = {}
        self._lock = RLock()

    def verify(
        self,
        mission_id: str,
        candidate,
        evidence: list[RegistryEvidence],
    ) -> RegistryVerificationResult:
        result = self._verifier.verify(candidate, evidence)
        with self._lock:
            history = self._results.setdefault(mission_id, [])
            if not history or history[-1].id != result.id:
                history.append(deepcopy(result))
            if result.human_review is not None:
                self._reviews[result.human_review.id] = deepcopy(result.human_review)
                self._review_mission[result.human_review.id] = mission_id
        return deepcopy(result)

    def decide(
        self,
        mission_id: str,
        review_id: str,
        *,
        decision: HumanReviewDecision,
        reviewer: str,
        note: str | None = None,
    ) -> HumanReviewDecisionRecord:
        with self._lock:
            review = self._reviews.get(review_id)
            if review is None or self._review_mission.get(review_id) != mission_id:
                raise KeyError(review_id)
            existing = self._decisions.get(review_id)
            if existing is not None:
                if (
                    existing.decision != decision
                    or existing.reviewer != reviewer
                    or existing.note != note
                ):
                    raise ValueError("human review decision is append-only")
                return deepcopy(existing)
            if decision.value not in review.allowed_decisions:
                raise ValueError("human review decision is not allowed")
            record = HumanReviewDecisionRecord(
                review_id=review_id,
                candidate_id=review.candidate_id,
                decision=decision,
                decided_at=datetime.now(UTC),
                reviewer=reviewer,
                note=note,
            )
            self._decisions[review_id] = record
            return deepcopy(record)

    def history(self, mission_id: str) -> RegistryVerificationHistory:
        with self._lock:
            if mission_id not in self._results:
                raise KeyError(mission_id)
            review_ids = {
                result.human_review.id
                for result in self._results[mission_id]
                if result.human_review is not None
            }
            return RegistryVerificationHistory(
                mission_id=mission_id,
                results=deepcopy(self._results[mission_id]),
                decisions=[
                    deepcopy(self._decisions[review_id])
                    for review_id in sorted(review_ids)
                    if review_id in self._decisions
                ],
            )

    @staticmethod
    def can_promote(result: RegistryVerificationResult) -> bool:
        return (
            result.state == RegistryVerificationState.VERIFIED
            and bool(result.accepted_identifier_ids)
            and not result.conflicts
            and result.human_review is None
        )


_COORDINATOR = RegistryVerificationCoordinator()


def get_registry_verification_coordinator() -> RegistryVerificationCoordinator:
    return _COORDINATOR


def reset_registry_verification_coordinator() -> None:
    global _COORDINATOR
    _COORDINATOR = RegistryVerificationCoordinator()
