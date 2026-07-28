from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.sef.models import (
    Claim,
    ClaimState,
    EvidenceRelation,
    Identifier,
    ReviewDecision,
    ReviewDecisionValue,
    SefBundle,
)


LEDGER_SCHEMA_VERSION = "0.1.0"


class LedgerModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceTier(StrEnum):
    AUTHORITY = "tier_1_authority"
    FIRST_PARTY = "tier_2_first_party"
    INDEPENDENT = "tier_3_independent"
    SIGNAL = "tier_4_signal"
    UNASSESSED = "unassessed"


class FreshnessState(StrEnum):
    CURRENT = "current"
    STALE = "stale"
    NOT_YET_VALID = "not_yet_valid"
    UNASSESSED = "unassessed"


class EffectiveReviewState(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"
    PENDING = "pending"


class ConflictState(StrEnum):
    UNRESOLVED = "unresolved"
    RESOLVED = "resolved"


class EvidenceMetadata(LedgerModel):
    id: Identifier
    mission_id: Identifier
    evidence_id: Identifier
    correlation_id: Identifier
    tier: EvidenceTier
    valid_at: datetime
    fresh_until: datetime | None = None
    recorded_at: datetime

    @model_validator(mode="after")
    def freshness_window_is_ordered(self) -> EvidenceMetadata:
        timestamps = [self.valid_at, self.recorded_at]
        if self.fresh_until is not None:
            timestamps.append(self.fresh_until)
        if any(item.tzinfo is None or item.utcoffset() is None for item in timestamps):
            raise ValueError("evidence metadata timestamps must be timezone-aware")
        if self.fresh_until is not None and self.fresh_until < self.valid_at:
            raise ValueError("fresh_until cannot be earlier than valid_at")
        return self


class PredicateFreshnessPolicy(LedgerModel):
    predicate: str = Field(min_length=1, max_length=300)
    max_age_days: int = Field(ge=0, le=36_500)
    accepted_tiers: list[EvidenceTier] = Field(
        default_factory=lambda: [
            EvidenceTier.AUTHORITY,
            EvidenceTier.FIRST_PARTY,
            EvidenceTier.INDEPENDENT,
        ],
        min_length=1,
    )


class LedgerPolicy(LedgerModel):
    default_max_age_days: int = Field(default=365, ge=0, le=36_500)
    default_accepted_tiers: list[EvidenceTier] = Field(
        default_factory=lambda: [
            EvidenceTier.AUTHORITY,
            EvidenceTier.FIRST_PARTY,
            EvidenceTier.INDEPENDENT,
        ],
        min_length=1,
    )
    predicates: list[PredicateFreshnessPolicy] = Field(default_factory=list)

    @model_validator(mode="after")
    def predicates_are_unique(self) -> LedgerPolicy:
        names = [item.predicate for item in self.predicates]
        if len(names) != len(set(names)):
            raise ValueError("duplicate predicate freshness policy")
        return self

    def for_predicate(self, predicate: str) -> PredicateFreshnessPolicy:
        for item in self.predicates:
            if item.predicate == predicate:
                return item
        return PredicateFreshnessPolicy(
            predicate=predicate,
            max_age_days=self.default_max_age_days,
            accepted_tiers=list(self.default_accepted_tiers),
        )


class EvidenceAssessment(LedgerModel):
    evidence_id: Identifier
    tier: EvidenceTier
    freshness: FreshnessState
    valid_at: datetime | None = None
    fresh_until: datetime | None = None
    accepted_for_predicate: bool


class ClaimConflictGroup(LedgerModel):
    id: Identifier
    mission_id: Identifier
    entity_id: Identifier
    predicate: str
    claim_ids: list[Identifier] = Field(min_length=2)
    state: ConflictState
    accepted_claim_id: Identifier | None = None


class ClaimLedgerEntry(LedgerModel):
    claim_id: Identifier
    state: ClaimState
    critical: bool
    review_state: EffectiveReviewState
    latest_review_decision_id: Identifier | None = None
    supporting_evidence: list[EvidenceAssessment] = Field(default_factory=list)
    contradicting_evidence_ids: list[Identifier] = Field(default_factory=list)
    conflict_group_ids: list[Identifier] = Field(default_factory=list)
    client_eligible: bool
    reason_codes: list[str] = Field(default_factory=list)


class LedgerSummary(LedgerModel):
    mission_id: Identifier
    as_of: datetime
    total_claims: int = Field(ge=0)
    confirmed_claims: int = Field(ge=0)
    client_eligible_claims: int = Field(ge=0)
    critical_claims: int = Field(ge=0)
    critical_eligible_claims: int = Field(ge=0)
    critical_coverage: float = Field(ge=0, le=1)
    unresolved_conflict_groups: int = Field(ge=0)
    stale_evidence: int = Field(ge=0)
    pending_review_claims: int = Field(ge=0)


class LedgerSnapshot(LedgerModel):
    schema_version: Literal["0.1.0"] = LEDGER_SCHEMA_VERSION
    mission_id: Identifier
    correlation_id: Identifier
    as_of: datetime
    evidence: list[EvidenceAssessment] = Field(default_factory=list)
    conflicts: list[ClaimConflictGroup] = Field(default_factory=list)
    claims: list[ClaimLedgerEntry] = Field(default_factory=list)
    summary: LedgerSummary


class LedgerRequest(LedgerModel):
    schema_version: Literal["0.1.0"] = LEDGER_SCHEMA_VERSION
    mission_id: Identifier
    as_of: datetime
    evidence_metadata: list[EvidenceMetadata] = Field(default_factory=list)
    policy: LedgerPolicy = Field(default_factory=LedgerPolicy)

    @model_validator(mode="after")
    def as_of_is_timezone_aware(self) -> LedgerRequest:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("ledger as_of must be timezone-aware")
        return self


class LedgerContract(LedgerModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "$id": "https://aimeton.ru/schemas/sef-ledger-v0.1.schema.json",
            "$schema": "https://json-schema.org/draft/2020-12/schema",
        },
    )

    request: LedgerRequest
    snapshot: LedgerSnapshot


def _stable_id(prefix: str, *parts: str) -> str:
    payload = "\x1f".join(parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(payload).hexdigest()[:24]}"


def _claim_value_key(claim: Claim) -> str:
    return json.dumps(
        claim.value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _latest_claim_reviews(
    decisions: list[ReviewDecision],
    mission_id: str,
    as_of: datetime,
) -> dict[str, ReviewDecision]:
    latest: dict[str, ReviewDecision] = {}
    for decision in decisions:
        if decision.mission_id != mission_id or decision.target_type != "claim":
            continue
        if decision.decided_at > as_of:
            continue
        current = latest.get(decision.target_id)
        if current is None or (decision.decided_at, decision.id) > (
            current.decided_at,
            current.id,
        ):
            latest[decision.target_id] = decision
    return latest


def _review_state(decision: ReviewDecision | None) -> EffectiveReviewState:
    if decision is None:
        return EffectiveReviewState.PENDING
    return EffectiveReviewState(decision.decision.value)


def _build_conflicts(
    claims: list[Claim],
    reviews: dict[str, ReviewDecision],
) -> list[ClaimConflictGroup]:
    grouped: dict[tuple[str, str, str], list[Claim]] = {}
    for claim in claims:
        grouped.setdefault(
            (claim.mission_id, claim.entity_id, claim.predicate),
            [],
        ).append(claim)

    conflicts: list[ClaimConflictGroup] = []
    for (mission_id, entity_id, predicate), candidates in grouped.items():
        if len({_claim_value_key(claim) for claim in candidates}) < 2:
            continue
        ordered = sorted(candidates, key=lambda item: item.id)
        approved = [
            claim.id
            for claim in ordered
            if reviews.get(claim.id) is not None
            and reviews[claim.id].decision == ReviewDecisionValue.APPROVED
            and reviews[claim.id].decided_at >= claim.created_at
        ]
        rejected = {
            claim.id
            for claim in ordered
            if reviews.get(claim.id) is not None
            and reviews[claim.id].decision == ReviewDecisionValue.REJECTED
            and reviews[claim.id].decided_at >= claim.created_at
        }
        resolved = len(approved) == 1 and rejected == {
            claim.id for claim in ordered if claim.id != approved[0]
        }
        conflicts.append(
            ClaimConflictGroup(
                id=_stable_id("conflict", mission_id, entity_id, predicate),
                mission_id=mission_id,
                entity_id=entity_id,
                predicate=predicate,
                claim_ids=[claim.id for claim in ordered],
                state=ConflictState.RESOLVED if resolved else ConflictState.UNRESOLVED,
                accepted_claim_id=approved[0] if resolved else None,
            )
        )
    return conflicts


def build_ledger_snapshot(
    bundle: SefBundle,
    request: LedgerRequest,
) -> LedgerSnapshot:
    mission = next(
        (item for item in bundle.missions if item.id == request.mission_id),
        None,
    )
    if mission is None:
        raise ValueError("ledger request references unknown mission")

    evidence_by_id = {
        item.id: item for item in bundle.evidence if item.mission_id == mission.id
    }
    metadata_by_evidence: dict[str, EvidenceMetadata] = {}
    metadata_ids: set[str] = set()
    for item in request.evidence_metadata:
        if item.id in metadata_ids:
            raise ValueError("duplicate evidence metadata id")
        metadata_ids.add(item.id)
        if item.evidence_id in metadata_by_evidence:
            raise ValueError("duplicate evidence metadata for evidence")
        evidence = evidence_by_id.get(item.evidence_id)
        if evidence is None or item.mission_id != mission.id:
            raise ValueError("evidence metadata references evidence outside the mission")
        if item.correlation_id != mission.correlation_id:
            raise ValueError("evidence metadata breaks mission correlation_id")
        metadata_by_evidence[item.evidence_id] = item

    claims = [item for item in bundle.claims if item.mission_id == mission.id]
    reviews = _latest_claim_reviews(bundle.review_decisions, mission.id, request.as_of)
    conflicts = _build_conflicts(claims, reviews)
    conflicts_by_claim: dict[str, list[ClaimConflictGroup]] = {}
    for group in conflicts:
        for claim_id in group.claim_ids:
            conflicts_by_claim.setdefault(claim_id, []).append(group)

    assessed_evidence: dict[tuple[str, str], EvidenceAssessment] = {}

    def assess(evidence_id: str, predicate: str) -> EvidenceAssessment:
        key = (evidence_id, predicate)
        existing = assessed_evidence.get(key)
        if existing is not None:
            return existing
        policy = request.policy.for_predicate(predicate)
        metadata = metadata_by_evidence.get(evidence_id)
        if metadata is None or metadata.recorded_at > request.as_of:
            result = EvidenceAssessment(
                evidence_id=evidence_id,
                tier=EvidenceTier.UNASSESSED,
                freshness=FreshnessState.UNASSESSED,
                accepted_for_predicate=False,
            )
        else:
            fresh_until = metadata.fresh_until or (
                metadata.valid_at + timedelta(days=policy.max_age_days)
            )
            if request.as_of < metadata.valid_at:
                freshness = FreshnessState.NOT_YET_VALID
            elif request.as_of <= fresh_until:
                freshness = FreshnessState.CURRENT
            else:
                freshness = FreshnessState.STALE
            result = EvidenceAssessment(
                evidence_id=evidence_id,
                tier=metadata.tier,
                freshness=freshness,
                valid_at=metadata.valid_at,
                fresh_until=fresh_until,
                accepted_for_predicate=metadata.tier in policy.accepted_tiers,
            )
        assessed_evidence[key] = result
        return result

    entries: list[ClaimLedgerEntry] = []
    for claim in sorted(claims, key=lambda item: item.id):
        decision = reviews.get(claim.id)
        review_state = _review_state(decision)
        support = [
            assess(link.evidence_id, claim.predicate)
            for link in claim.evidence_refs
            if link.relation == EvidenceRelation.SUPPORTS
        ]
        contradicting = sorted(
            link.evidence_id
            for link in claim.evidence_refs
            if link.relation == EvidenceRelation.CONTRADICTS
        )
        claim_conflicts = conflicts_by_claim.get(claim.id, [])
        unresolved = any(
            group.state == ConflictState.UNRESOLVED for group in claim_conflicts
        )
        losing_resolution = any(
            group.state == ConflictState.RESOLVED
            and group.accepted_claim_id != claim.id
            for group in claim_conflicts
        )
        current_support = [
            item
            for item in support
            if item.accepted_for_predicate
            and item.freshness == FreshnessState.CURRENT
        ]
        stale_support = [
            item
            for item in support
            if item.accepted_for_predicate
            and item.freshness == FreshnessState.STALE
        ]
        review_floor = claim.created_at
        referenced_evidence = [
            evidence_by_id[link.evidence_id]
            for link in claim.evidence_refs
            if link.evidence_id in evidence_by_id
        ]
        if referenced_evidence:
            review_floor = max(
                review_floor,
                *(item.observed_at for item in referenced_evidence),
            )
        review_covers_claim_evidence = (
            decision is not None and decision.decided_at >= review_floor
        )
        effective_approval = (
            review_state == EffectiveReviewState.APPROVED
            and review_covers_claim_evidence
        )
        stale_override = effective_approval and all(
            item.fresh_until is not None
            and decision is not None
            and decision.decided_at >= item.fresh_until
            for item in stale_support
        )
        reasons: list[str] = []
        if claim.state != ClaimState.CONFIRMED:
            reasons.append("claim_not_confirmed")
        if not support:
            reasons.append("supporting_evidence_missing")
        elif not current_support and not stale_support:
            reasons.append("admissible_evidence_missing")
        elif not current_support and not stale_override:
            reasons.append("stale_evidence_requires_approval")
        if contradicting and not effective_approval:
            reasons.append("contradicting_evidence_requires_approval")
        if (
            review_state == EffectiveReviewState.APPROVED
            and not review_covers_claim_evidence
        ):
            reasons.append("review_predates_claim_or_evidence")
        if review_state == EffectiveReviewState.REJECTED:
            reasons.append("claim_rejected")
        elif review_state == EffectiveReviewState.NEEDS_MORE_EVIDENCE:
            reasons.append("review_requires_more_evidence")
        elif claim.critical and not effective_approval:
            reasons.append("critical_claim_requires_approval")
        if unresolved:
            reasons.append("unresolved_conflict")
        if losing_resolution:
            reasons.append("conflict_resolved_to_other_claim")
        client_eligible = not reasons
        entries.append(
            ClaimLedgerEntry(
                claim_id=claim.id,
                state=claim.state,
                critical=claim.critical,
                review_state=review_state,
                latest_review_decision_id=decision.id if decision else None,
                supporting_evidence=support,
                contradicting_evidence_ids=contradicting,
                conflict_group_ids=[group.id for group in claim_conflicts],
                client_eligible=client_eligible,
                reason_codes=reasons,
            )
        )

    unique_evidence: dict[str, EvidenceAssessment] = {}
    for entry in entries:
        for item in entry.supporting_evidence:
            current = unique_evidence.get(item.evidence_id)
            if current is None or (
                current.freshness == FreshnessState.CURRENT
                and item.freshness != FreshnessState.CURRENT
            ):
                unique_evidence[item.evidence_id] = item

    critical = [entry for entry in entries if entry.critical]
    critical_eligible = [entry for entry in critical if entry.client_eligible]
    pending_review = [
        entry
        for entry in entries
        if entry.review_state == EffectiveReviewState.PENDING
        and (
            entry.critical
            or "unresolved_conflict" in entry.reason_codes
            or "stale_evidence_requires_approval" in entry.reason_codes
            or "contradicting_evidence_requires_approval" in entry.reason_codes
        )
    ]
    summary = LedgerSummary(
        mission_id=mission.id,
        as_of=request.as_of,
        total_claims=len(entries),
        confirmed_claims=sum(entry.state == ClaimState.CONFIRMED for entry in entries),
        client_eligible_claims=sum(entry.client_eligible for entry in entries),
        critical_claims=len(critical),
        critical_eligible_claims=len(critical_eligible),
        critical_coverage=(
            len(critical_eligible) / len(critical) if critical else 1.0
        ),
        unresolved_conflict_groups=sum(
            group.state == ConflictState.UNRESOLVED for group in conflicts
        ),
        stale_evidence=sum(
            item.freshness == FreshnessState.STALE
            for item in unique_evidence.values()
        ),
        pending_review_claims=len(pending_review),
    )
    return LedgerSnapshot(
        mission_id=mission.id,
        correlation_id=mission.correlation_id,
        as_of=request.as_of,
        evidence=sorted(unique_evidence.values(), key=lambda item: item.evidence_id),
        conflicts=conflicts,
        claims=entries,
        summary=summary,
    )


def require_client_eligible_claims(
    snapshot: LedgerSnapshot,
    claim_ids: list[str],
) -> None:
    entries = {item.claim_id: item for item in snapshot.claims}
    blocked: dict[str, list[str]] = {}
    for claim_id in claim_ids:
        entry = entries.get(claim_id)
        if entry is None:
            blocked[claim_id] = ["claim_missing_from_ledger"]
        elif not entry.client_eligible:
            blocked[claim_id] = list(entry.reason_codes)
    if blocked:
        details = "; ".join(
            f"{claim_id}={','.join(reasons)}"
            for claim_id, reasons in sorted(blocked.items())
        )
        raise ValueError(f"client-facing claims are not ledger eligible: {details}")
