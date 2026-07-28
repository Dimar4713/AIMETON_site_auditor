from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

from app.sef.ledger import (
    ConflictState,
    EvidenceTier,
    FreshnessState,
    LedgerRequest,
    LedgerSnapshot,
    build_ledger_snapshot,
)
from app.sef.models import (
    Claim,
    ClaimState,
    ClaimValue,
    EvidenceRelation,
    Identifier,
    SefBundle,
    SourceKind,
)


COMPANY_PROFILE_SCHEMA_VERSION = "0.1.0"


class ProfileModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProfileSectionCode(StrEnum):
    IDENTITY = "identity"
    OFFICIAL_PRESENCE = "official_presence"
    CONTACTS = "contacts"
    WORKFORCE = "workforce"
    FINANCIALS = "financials"
    LEADERSHIP_AND_FOUNDERS = "leadership_and_founders"
    OWNERSHIP_AND_AFFILIATIONS = "ownership_and_affiliations"
    LEGAL_EVENTS = "legal_events"
    MARKET_SIGNALS = "market_signals"
    BUSINESS_MACHINE = "business_machine"
    ECONOMIC_SIGNALS = "economic_signals"
    AI_OPPORTUNITY = "ai_opportunity"
    RISKS_GAPS_CONFLICTS = "risks_gaps_conflicts"
    EVIDENCE_APPENDIX = "evidence_appendix"


class ProfileFieldStatus(StrEnum):
    VERIFIED = "verified"
    HYPOTHESIS = "hypothesis"
    NOT_FOUND = "not_found"
    BLOCKED = "blocked"


class ProfileSectionStatus(StrEnum):
    VERIFIED = "verified"
    PARTIAL = "partial"
    MISSING = "missing"
    BLOCKED = "blocked"


class CriticalGapCode(StrEnum):
    CONTACTS = "contacts"
    WORKFORCE = "workforce"
    FINANCIALS = "financials"
    OWNERSHIP = "ownership"
    AFFILIATIONS = "affiliations"
    LEGAL_EVENTS = "legal_events"


class CriticalGapStatus(StrEnum):
    CLOSED = "closed"
    HYPOTHESIS = "hypothesis"
    BLOCKED = "blocked"
    MISSING = "missing"


class CompanyProfileField(ProfileModel):
    claim_id: Identifier
    section: ProfileSectionCode
    predicate: str = Field(min_length=1, max_length=300)
    value: ClaimValue
    period: str | None = Field(default=None, max_length=200)
    status: ProfileFieldStatus
    critical: bool
    client_eligible: bool
    evidence_ids: list[Identifier] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)


class CompanyProfileSection(ProfileModel):
    code: ProfileSectionCode
    title: str = Field(min_length=1, max_length=300)
    status: ProfileSectionStatus
    fields: list[CompanyProfileField] = Field(default_factory=list)


class ProfileEvidenceClaimAssessment(ProfileModel):
    claim_id: Identifier
    tier: EvidenceTier
    freshness: FreshnessState


class ProfileEvidenceItem(ProfileModel):
    evidence_id: Identifier
    source_id: Identifier
    source_kind: SourceKind
    publisher: str
    document_id: Identifier
    document_url: AnyHttpUrl
    document_title: str
    document_accessed_at: datetime
    document_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    quote: str = Field(min_length=1, max_length=8000)
    locator: str = Field(min_length=1, max_length=1000)
    evidence_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    claim_assessments: list[ProfileEvidenceClaimAssessment] = Field(min_length=1)


class CriticalGapAssessment(ProfileModel):
    code: CriticalGapCode
    status: CriticalGapStatus
    closed: bool
    claim_ids: list[Identifier] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)


class CompanyProfileSummary(ProfileModel):
    required_sections: int = Field(default=14, ge=14, le=14)
    verified_sections: int = Field(ge=0, le=14)
    section_coverage: float = Field(ge=0, le=1)
    critical_gaps: int = Field(default=6, ge=6, le=6)
    closed_critical_gaps: int = Field(ge=0, le=6)
    critical_gap_coverage: float = Field(ge=0, le=1)
    verified_fields: int = Field(ge=0)
    hypothesis_fields: int = Field(ge=0)
    blocked_fields: int = Field(ge=0)
    unresolved_conflicts: int = Field(ge=0)
    profile_gate_passed: bool
    client_release_ready: bool
    release_blockers: list[str] = Field(default_factory=list)


class CompanyProfileV1(ProfileModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "$id": "https://aimeton.ru/schemas/sef-company-profile-v0.1.schema.json",
            "$schema": "https://json-schema.org/draft/2020-12/schema",
        },
    )

    schema_version: Literal["0.1.0"] = COMPANY_PROFILE_SCHEMA_VERSION
    id: Identifier
    mission_id: Identifier
    entity_id: Identifier
    correlation_id: Identifier
    as_of: datetime
    canonical_name: str
    sections: list[CompanyProfileSection] = Field(min_length=14, max_length=14)
    critical_gap_assessments: list[CriticalGapAssessment] = Field(
        min_length=6,
        max_length=6,
    )
    evidence_appendix: list[ProfileEvidenceItem] = Field(default_factory=list)
    summary: CompanyProfileSummary


class CompanyProfileBuildRequest(ProfileModel):
    bundle: SefBundle
    ledger_request: LedgerRequest
    entity_id: Identifier


SECTION_TITLES: dict[ProfileSectionCode, str] = {
    ProfileSectionCode.IDENTITY: "Идентичность компании",
    ProfileSectionCode.OFFICIAL_PRESENCE: "Официальный сайт и домены",
    ProfileSectionCode.CONTACTS: "Контакты",
    ProfileSectionCode.WORKFORCE: "Численность и кадровые сигналы",
    ProfileSectionCode.FINANCIALS: "Финансы и налоги",
    ProfileSectionCode.LEADERSHIP_AND_FOUNDERS: "Руководители и учредители",
    ProfileSectionCode.OWNERSHIP_AND_AFFILIATIONS: "Владельцы и аффилированность",
    ProfileSectionCode.LEGAL_EVENTS: "Суды, взыскания и банкротства",
    ProfileSectionCode.MARKET_SIGNALS: "Закупки, вакансии, новости и отзывы",
    ProfileSectionCode.BUSINESS_MACHINE: "Бизнес-машина AIMETON",
    ProfileSectionCode.ECONOMIC_SIGNALS: "Экономические сигналы",
    ProfileSectionCode.AI_OPPORTUNITY: "Главная AI-возможность и решения",
    ProfileSectionCode.RISKS_GAPS_CONFLICTS: "Риски, пробелы и противоречия",
    ProfileSectionCode.EVIDENCE_APPENDIX: "Приложение доказательств",
}


PREDICATE_SECTIONS: dict[str, ProfileSectionCode] = {
    "legal_name": ProfileSectionCode.IDENTITY,
    "brand_name": ProfileSectionCode.IDENTITY,
    "inn": ProfileSectionCode.IDENTITY,
    "ogrn": ProfileSectionCode.IDENTITY,
    "registration_status": ProfileSectionCode.IDENTITY,
    "address": ProfileSectionCode.IDENTITY,
    "website": ProfileSectionCode.OFFICIAL_PRESENCE,
    "official_website": ProfileSectionCode.OFFICIAL_PRESENCE,
    "domain": ProfileSectionCode.OFFICIAL_PRESENCE,
    "domains": ProfileSectionCode.OFFICIAL_PRESENCE,
    "phone": ProfileSectionCode.CONTACTS,
    "phones": ProfileSectionCode.CONTACTS,
    "email": ProfileSectionCode.CONTACTS,
    "emails": ProfileSectionCode.CONTACTS,
    "contact": ProfileSectionCode.CONTACTS,
    "contacts": ProfileSectionCode.CONTACTS,
    "headcount": ProfileSectionCode.WORKFORCE,
    "workforce_size": ProfileSectionCode.WORKFORCE,
    "workforce_signal": ProfileSectionCode.WORKFORCE,
    "staff_signal": ProfileSectionCode.WORKFORCE,
    "revenue": ProfileSectionCode.FINANCIALS,
    "profit": ProfileSectionCode.FINANCIALS,
    "assets": ProfileSectionCode.FINANCIALS,
    "taxes": ProfileSectionCode.FINANCIALS,
    "executive": ProfileSectionCode.LEADERSHIP_AND_FOUNDERS,
    "executives": ProfileSectionCode.LEADERSHIP_AND_FOUNDERS,
    "founder": ProfileSectionCode.LEADERSHIP_AND_FOUNDERS,
    "founders": ProfileSectionCode.LEADERSHIP_AND_FOUNDERS,
    "owner": ProfileSectionCode.OWNERSHIP_AND_AFFILIATIONS,
    "owners": ProfileSectionCode.OWNERSHIP_AND_AFFILIATIONS,
    "beneficial_owner": ProfileSectionCode.OWNERSHIP_AND_AFFILIATIONS,
    "beneficial_owners": ProfileSectionCode.OWNERSHIP_AND_AFFILIATIONS,
    "affiliate": ProfileSectionCode.OWNERSHIP_AND_AFFILIATIONS,
    "affiliates": ProfileSectionCode.OWNERSHIP_AND_AFFILIATIONS,
    "affiliated_entity": ProfileSectionCode.OWNERSHIP_AND_AFFILIATIONS,
    "related_party": ProfileSectionCode.OWNERSHIP_AND_AFFILIATIONS,
    "court_case": ProfileSectionCode.LEGAL_EVENTS,
    "arbitration_case": ProfileSectionCode.LEGAL_EVENTS,
    "enforcement_event": ProfileSectionCode.LEGAL_EVENTS,
    "bankruptcy_event": ProfileSectionCode.LEGAL_EVENTS,
    "legal_events_summary": ProfileSectionCode.LEGAL_EVENTS,
    "procurement": ProfileSectionCode.MARKET_SIGNALS,
    "vacancy": ProfileSectionCode.MARKET_SIGNALS,
    "news_event": ProfileSectionCode.MARKET_SIGNALS,
    "review_signal": ProfileSectionCode.MARKET_SIGNALS,
    "business_machine_cell": ProfileSectionCode.BUSINESS_MACHINE,
    "economic_signal": ProfileSectionCode.ECONOMIC_SIGNALS,
    "ai_opportunity": ProfileSectionCode.AI_OPPORTUNITY,
    "ai_solution": ProfileSectionCode.AI_OPPORTUNITY,
    "risk": ProfileSectionCode.RISKS_GAPS_CONFLICTS,
    "gap": ProfileSectionCode.RISKS_GAPS_CONFLICTS,
}


GAP_PREDICATES: dict[CriticalGapCode, set[str]] = {
    CriticalGapCode.CONTACTS: {"phone", "phones", "email", "emails", "contact", "contacts"},
    CriticalGapCode.WORKFORCE: {
        "headcount",
        "workforce_size",
        "workforce_signal",
        "staff_signal",
    },
    CriticalGapCode.FINANCIALS: {"revenue", "profit", "assets", "taxes"},
    CriticalGapCode.OWNERSHIP: {
        "owner",
        "owners",
        "beneficial_owner",
        "beneficial_owners",
        "founder",
        "founders",
    },
    CriticalGapCode.AFFILIATIONS: {
        "affiliate",
        "affiliates",
        "affiliated_entity",
        "related_party",
    },
    CriticalGapCode.LEGAL_EVENTS: {
        "court_case",
        "arbitration_case",
        "enforcement_event",
        "bankruptcy_event",
        "legal_events_summary",
    },
}


FINANCIAL_PREDICATES = GAP_PREDICATES[CriticalGapCode.FINANCIALS]


def _normalise_predicate(value: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", value.strip().lower())).strip("_")


def _section_for(predicate: str) -> ProfileSectionCode:
    normalised = _normalise_predicate(predicate)
    if normalised.startswith("km_"):
        return ProfileSectionCode.BUSINESS_MACHINE
    return PREDICATE_SECTIONS.get(
        normalised,
        ProfileSectionCode.RISKS_GAPS_CONFLICTS,
    )


def _period_from_claim(claim: Claim) -> str | None:
    if isinstance(claim.value, dict):
        period = claim.value.get("period")
        if period is not None and str(period).strip():
            return str(period).strip()
    return None


def _field_status(claim: Claim, client_eligible: bool) -> ProfileFieldStatus:
    if client_eligible:
        return ProfileFieldStatus.VERIFIED
    if claim.state == ClaimState.CANDIDATE:
        return ProfileFieldStatus.HYPOTHESIS
    if claim.state == ClaimState.NOT_FOUND:
        return ProfileFieldStatus.NOT_FOUND
    return ProfileFieldStatus.BLOCKED


def _profile_id(
    bundle: SefBundle,
    ledger: LedgerSnapshot,
    entity_id: str,
) -> str:
    claims = [
        item.model_dump(mode="json")
        for item in bundle.claims
        if item.mission_id == ledger.mission_id and item.entity_id == entity_id
    ]
    payload = json.dumps(
        {
            "entity_id": entity_id,
            "claims": claims,
            "ledger": ledger.model_dump(mode="json"),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"profile_{hashlib.sha256(payload).hexdigest()[:24]}"


def _build_evidence_appendix(
    *,
    bundle: SefBundle,
    ledger: LedgerSnapshot,
    fields: list[CompanyProfileField],
) -> list[ProfileEvidenceItem]:
    evidence_by_id = {item.id: item for item in bundle.evidence}
    documents = {item.id: item for item in bundle.documents}
    sources = {item.id: item for item in bundle.sources}
    ledger_claims = {item.claim_id: item for item in ledger.claims}
    claim_ids_by_evidence: dict[str, set[str]] = {}
    assessments: dict[
        tuple[str, str],
        ProfileEvidenceClaimAssessment,
    ] = {}

    for field in fields:
        entry = ledger_claims.get(field.claim_id)
        if entry is None:
            continue
        for assessment in entry.supporting_evidence:
            if assessment.evidence_id not in field.evidence_ids:
                continue
            claim_ids_by_evidence.setdefault(assessment.evidence_id, set()).add(field.claim_id)
            assessments[(assessment.evidence_id, field.claim_id)] = (
                ProfileEvidenceClaimAssessment(
                    claim_id=field.claim_id,
                    tier=assessment.tier,
                    freshness=assessment.freshness,
                )
            )

    result: list[ProfileEvidenceItem] = []
    for evidence_id, claim_ids in sorted(claim_ids_by_evidence.items()):
        evidence = evidence_by_id.get(evidence_id)
        if evidence is None:
            raise ValueError("profile claim references evidence missing from bundle")
        document = documents.get(evidence.document_id)
        source = sources.get(evidence.source_id)
        if document is None or source is None or document.content_digest is None:
            raise ValueError("profile evidence requires fetched document and source")
        ordered_claim_ids = sorted(claim_ids)
        result.append(
            ProfileEvidenceItem(
                evidence_id=evidence.id,
                source_id=source.id,
                source_kind=source.kind,
                publisher=source.publisher,
                document_id=document.id,
                document_url=document.url,
                document_title=document.title,
                document_accessed_at=document.accessed_at,
                document_digest=document.content_digest,
                quote=evidence.quote,
                locator=evidence.locator,
                evidence_digest=evidence.digest,
                claim_assessments=[
                    assessments[(evidence_id, claim_id)]
                    for claim_id in ordered_claim_ids
                ],
            )
        )
    return result


def _section_status(fields: list[CompanyProfileField]) -> ProfileSectionStatus:
    if not fields:
        return ProfileSectionStatus.MISSING
    verified = [item for item in fields if item.status == ProfileFieldStatus.VERIFIED]
    if len(verified) == len(fields):
        return ProfileSectionStatus.VERIFIED
    if verified:
        return ProfileSectionStatus.PARTIAL
    if any(item.status == ProfileFieldStatus.HYPOTHESIS for item in fields):
        return ProfileSectionStatus.PARTIAL
    return ProfileSectionStatus.BLOCKED


def _assess_gap(
    code: CriticalGapCode,
    fields: list[CompanyProfileField],
) -> CriticalGapAssessment:
    predicates = GAP_PREDICATES[code]
    relevant = [
        item for item in fields if _normalise_predicate(item.predicate) in predicates
    ]
    verified = [
        item
        for item in relevant
        if item.status == ProfileFieldStatus.VERIFIED
        and item.client_eligible
        and item.evidence_ids
    ]
    if verified:
        return CriticalGapAssessment(
            code=code,
            status=CriticalGapStatus.CLOSED,
            closed=True,
            claim_ids=[item.claim_id for item in verified],
        )
    if any(item.status == ProfileFieldStatus.HYPOTHESIS for item in relevant):
        status = CriticalGapStatus.HYPOTHESIS
        reasons = ["hypothesis_does_not_close_critical_gap"]
    elif relevant:
        status = CriticalGapStatus.BLOCKED
        reasons = sorted(
            {
                reason
                for item in relevant
                for reason in item.reason_codes
            }
            or {"critical_gap_has_no_verified_claim"}
        )
    else:
        status = CriticalGapStatus.MISSING
        reasons = ["critical_gap_has_no_claim"]
    return CriticalGapAssessment(
        code=code,
        status=status,
        closed=False,
        claim_ids=[item.claim_id for item in relevant],
        reason_codes=reasons,
    )


def build_company_profile(
    bundle: SefBundle,
    ledger: LedgerSnapshot,
    entity_id: str,
) -> CompanyProfileV1:
    mission = next(
        (item for item in bundle.missions if item.id == ledger.mission_id),
        None,
    )
    if mission is None:
        raise ValueError("company profile ledger references unknown mission")
    if mission.correlation_id != ledger.correlation_id:
        raise ValueError("company profile ledger breaks mission correlation_id")
    entity = next(
        (
            item
            for item in bundle.entities
            if item.id == entity_id and item.mission_id == mission.id
        ),
        None,
    )
    if entity is None or entity.entity_type != "company":
        raise ValueError("company profile requires a company entity in the ledger mission")
    if ledger.summary.mission_id != mission.id or ledger.summary.as_of != ledger.as_of:
        raise ValueError("company profile ledger summary is inconsistent")

    ledger_claims = {item.claim_id: item for item in ledger.claims}
    fields: list[CompanyProfileField] = []
    for claim in sorted(
        (
            item
            for item in bundle.claims
            if item.mission_id == mission.id and item.entity_id == entity.id
        ),
        key=lambda item: item.id,
    ):
        entry = ledger_claims.get(claim.id)
        reasons = (
            list(entry.reason_codes)
            if entry is not None
            else ["claim_missing_from_ledger"]
        )
        eligible = bool(entry and entry.client_eligible)
        supporting_ids = sorted(
            {
                link.evidence_id
                for link in claim.evidence_refs
                if link.relation == EvidenceRelation.SUPPORTS
            }
        )
        if eligible and not supporting_ids:
            raise ValueError("ledger-eligible profile claim has no supporting evidence")
        predicate = _normalise_predicate(claim.predicate)
        period = _period_from_claim(claim)
        if eligible and predicate in FINANCIAL_PREDICATES and period is None:
            eligible = False
            reasons.append("financial_period_missing")
        fields.append(
            CompanyProfileField(
                claim_id=claim.id,
                section=_section_for(predicate),
                predicate=predicate,
                value=claim.value,
                period=period,
                status=_field_status(claim, eligible),
                critical=claim.critical,
                client_eligible=eligible,
                evidence_ids=supporting_ids,
                reason_codes=sorted(set(reasons)),
            )
        )

    appendix = _build_evidence_appendix(
        bundle=bundle,
        ledger=ledger,
        fields=fields,
    )
    fields_by_section = {
        code: [item for item in fields if item.section == code]
        for code in ProfileSectionCode
    }
    sections: list[CompanyProfileSection] = []
    for code in ProfileSectionCode:
        section_fields = fields_by_section[code]
        status = _section_status(section_fields)
        if code == ProfileSectionCode.EVIDENCE_APPENDIX and appendix:
            status = ProfileSectionStatus.VERIFIED
        sections.append(
            CompanyProfileSection(
                code=code,
                title=SECTION_TITLES[code],
                status=status,
                fields=section_fields,
            )
        )

    gap_assessments = [_assess_gap(code, fields) for code in CriticalGapCode]
    closed_gaps = sum(item.closed for item in gap_assessments)
    verified_sections = sum(
        item.status == ProfileSectionStatus.VERIFIED for item in sections
    )
    unresolved_conflicts = sum(
        item.state == ConflictState.UNRESOLVED for item in ledger.conflicts
    )
    profile_gate_passed = (
        closed_gaps == len(CriticalGapCode) and unresolved_conflicts == 0
    )
    release_blockers = []
    if not profile_gate_passed:
        release_blockers.append("company_profile_gate_not_passed")
    release_blockers.append("human_review_and_signed_report_required")
    summary = CompanyProfileSummary(
        verified_sections=verified_sections,
        section_coverage=verified_sections / len(ProfileSectionCode),
        closed_critical_gaps=closed_gaps,
        critical_gap_coverage=closed_gaps / len(CriticalGapCode),
        verified_fields=sum(
            item.status == ProfileFieldStatus.VERIFIED for item in fields
        ),
        hypothesis_fields=sum(
            item.status == ProfileFieldStatus.HYPOTHESIS for item in fields
        ),
        blocked_fields=sum(
            item.status in {ProfileFieldStatus.BLOCKED, ProfileFieldStatus.NOT_FOUND}
            for item in fields
        ),
        unresolved_conflicts=unresolved_conflicts,
        profile_gate_passed=profile_gate_passed,
        client_release_ready=False,
        release_blockers=release_blockers,
    )
    return CompanyProfileV1(
        id=_profile_id(bundle, ledger, entity.id),
        mission_id=mission.id,
        entity_id=entity.id,
        correlation_id=mission.correlation_id,
        as_of=ledger.as_of,
        canonical_name=entity.canonical_name,
        sections=sections,
        critical_gap_assessments=gap_assessments,
        evidence_appendix=appendix,
        summary=summary,
    )


def build_company_profile_from_request(
    request: CompanyProfileBuildRequest,
) -> CompanyProfileV1:
    snapshot = build_ledger_snapshot(request.bundle, request.ledger_request)
    return build_company_profile(request.bundle, snapshot, request.entity_id)
