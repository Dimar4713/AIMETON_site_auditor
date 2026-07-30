from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import StrEnum

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

from app.entity_resolution.models import IdentityCandidate
from app.sef.models import Digest, Identifier


class RegistryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegistryAuthority(StrEnum):
    FNS_EGRUL = "fns_egrul"
    FNS_EGRIP = "fns_egrip"


class RegistryVerificationState(StrEnum):
    VERIFIED = "verified"
    CONFLICTING = "conflicting"
    UNRESOLVED = "unresolved"
    REVIEW_REQUIRED = "review_required"


class EntityRelationshipRole(StrEnum):
    SUBJECT = "subject"
    BRANCH = "branch"
    BRAND = "brand"
    OWNER = "owner"
    AFFILIATE = "affiliate"


class RegistryEvidence(RegistryModel):
    id: Identifier
    authority: RegistryAuthority
    source_url: AnyHttpUrl
    locator: str = Field(min_length=1, max_length=1_000)
    accessed_at: datetime
    document_digest: Digest
    legal_name: str = Field(min_length=1, max_length=500)
    inn: str | None = Field(default=None, pattern=r"^(?:\d{10}|\d{12})$")
    ogrn: str | None = Field(default=None, pattern=r"^(?:\d{13}|\d{15})$")
    relationship_role: EntityRelationshipRole = EntityRelationshipRole.SUBJECT
    lifecycle_state: str = "evidence"


class IdentifierVerification(RegistryModel):
    scheme: str = Field(min_length=1, max_length=100)
    candidate_value: str = Field(min_length=1, max_length=500)
    registry_value: str | None = Field(default=None, max_length=500)
    matched: bool
    evidence_id: Identifier | None = None
    reason: str = Field(min_length=1, max_length=500)


class HumanReviewRequest(RegistryModel):
    id: Identifier
    candidate_id: Identifier
    reason_codes: list[str] = Field(min_length=1)
    evidence_ids: list[Identifier] = Field(default_factory=list)
    allowed_decisions: list[str] = Field(
        default_factory=lambda: ["accept", "reject", "request_more_evidence"]
    )
    lifecycle_state: str = "pending"


class RegistryVerificationResult(RegistryModel):
    schema_version: str = "0.1.0"
    id: Identifier
    candidate_id: Identifier
    state: RegistryVerificationState
    authority: RegistryAuthority | None = None
    evidence_ids: list[Identifier] = Field(default_factory=list)
    identifier_checks: list[IdentifierVerification] = Field(default_factory=list)
    accepted_identifier_ids: list[Identifier] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    human_review: HumanReviewRequest | None = None


def _stable_id(prefix: str, *parts: object) -> str:
    encoded = json.dumps(
        parts,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(encoded).hexdigest()[:24]}"


def _normalized_legal_name(value: str) -> str:
    normalized = " ".join(
        re.sub(r"[^\w]+", " ", value.casefold(), flags=re.UNICODE).split()
    )
    aliases = (
        (r"^общество с ограниченной ответственностью\b", "ооо"),
        (r"^публичное акционерное общество\b", "пао"),
        (r"^акционерное общество\b", "ао"),
        (r"^индивидуальный предприниматель\b", "ип"),
    )
    for expression, replacement in aliases:
        normalized = re.sub(expression, replacement, normalized, count=1)
    return normalized


def _identifier_map(candidate: IdentityCandidate) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for identifier in candidate.identifiers:
        result.setdefault(identifier.scheme, set()).add(identifier.normalized_value)
    return result


class OfficialRegistryVerifier:
    """Fail-closed verifier for already fetched official registry evidence.

    Network access is intentionally outside this class. A registry connector must first
    fetch and persist the authoritative document, then pass locator-bound evidence here.
    """

    def verify(
        self,
        candidate: IdentityCandidate,
        evidence: list[RegistryEvidence],
    ) -> RegistryVerificationResult:
        result_id = _stable_id(
            "registry_verification",
            candidate.id,
            [item.model_dump(mode="json") for item in evidence],
        )
        if not evidence:
            return RegistryVerificationResult(
                id=result_id,
                candidate_id=candidate.id,
                state=RegistryVerificationState.UNRESOLVED,
                gaps=["official_registry_evidence_missing"],
            )

        subject_evidence = [
            item
            for item in evidence
            if item.relationship_role == EntityRelationshipRole.SUBJECT
        ]
        non_subject = [
            item
            for item in evidence
            if item.relationship_role != EntityRelationshipRole.SUBJECT
        ]
        reason_codes: list[str] = []
        if non_subject:
            reason_codes.append("registry_relationship_scope_requires_review")
        if not subject_evidence:
            reason_codes.append("registry_subject_record_missing")

        authorities = {item.authority for item in subject_evidence}
        if len(authorities) > 1:
            reason_codes.append("multiple_registry_authorities")

        identifiers = _identifier_map(candidate)
        checks: list[IdentifierVerification] = []
        accepted_ids: list[str] = []
        conflicts: list[str] = []

        for scheme in ("inn", "ogrn"):
            candidate_values = identifiers.get(scheme, set())
            registry_values = {
                value
                for item in subject_evidence
                for value in [getattr(item, scheme)]
                if value
            }
            if not candidate_values:
                checks.append(
                    IdentifierVerification(
                        scheme=scheme,
                        candidate_value="missing",
                        registry_value=next(iter(registry_values), None),
                        matched=False,
                        reason=f"candidate_{scheme}_missing",
                    )
                )
                continue
            for candidate_value in sorted(candidate_values):
                matched_evidence = next(
                    (
                        item
                        for item in subject_evidence
                        if getattr(item, scheme) == candidate_value
                    ),
                    None,
                )
                matched = matched_evidence is not None
                checks.append(
                    IdentifierVerification(
                        scheme=scheme,
                        candidate_value=candidate_value,
                        registry_value=(
                            candidate_value
                            if matched
                            else next(iter(sorted(registry_values)), None)
                        ),
                        matched=matched,
                        evidence_id=matched_evidence.id if matched_evidence else None,
                        reason=(
                            "exact_authoritative_match"
                            if matched
                            else f"authoritative_{scheme}_mismatch"
                        ),
                    )
                )
                if matched and matched_evidence is not None:
                    accepted_ids.append(
                        _stable_id(
                            "accepted_identifier_link",
                            candidate.id,
                            scheme,
                            candidate_value,
                            matched_evidence.id,
                            matched_evidence.locator,
                        )
                    )
                elif registry_values:
                    conflicts.append(f"authoritative_{scheme}_mismatch")

        candidate_names = identifiers.get("legal_name", set()) or {
            _normalized_legal_name(candidate.canonical_name)
        }
        registry_names = {
            _normalized_legal_name(item.legal_name) for item in subject_evidence
        }
        if registry_names and candidate_names.isdisjoint(registry_names):
            conflicts.append("authoritative_legal_name_mismatch")

        if conflicts:
            reason_codes.extend(conflicts)
        if len(subject_evidence) > 1:
            subject_keys = {(item.inn, item.ogrn) for item in subject_evidence}
            if len(subject_keys) > 1:
                reason_codes.append("multiple_subject_records")

        if reason_codes:
            review = HumanReviewRequest(
                id=_stable_id(
                    "identity_review",
                    candidate.id,
                    sorted(set(reason_codes)),
                    sorted(item.id for item in evidence),
                ),
                candidate_id=candidate.id,
                reason_codes=sorted(set(reason_codes)),
                evidence_ids=sorted(item.id for item in evidence),
            )
            state = (
                RegistryVerificationState.CONFLICTING
                if conflicts
                else RegistryVerificationState.REVIEW_REQUIRED
            )
            return RegistryVerificationResult(
                id=result_id,
                candidate_id=candidate.id,
                state=state,
                authority=next(iter(authorities), None),
                evidence_ids=sorted(item.id for item in evidence),
                identifier_checks=checks,
                conflicts=sorted(set(conflicts)),
                gaps=["human_identity_review"],
                human_review=review,
            )

        strong_matches = {
            item.scheme for item in checks if item.matched and item.scheme in {"inn", "ogrn"}
        }
        if not strong_matches:
            return RegistryVerificationResult(
                id=result_id,
                candidate_id=candidate.id,
                state=RegistryVerificationState.UNRESOLVED,
                authority=next(iter(authorities), None),
                evidence_ids=sorted(item.id for item in evidence),
                identifier_checks=checks,
                gaps=["official_registry_identifier_missing"],
            )

        return RegistryVerificationResult(
            id=result_id,
            candidate_id=candidate.id,
            state=RegistryVerificationState.VERIFIED,
            authority=next(iter(authorities)),
            evidence_ids=sorted(item.id for item in evidence),
            identifier_checks=checks,
            accepted_identifier_ids=sorted(set(accepted_ids)),
        )
