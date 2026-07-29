from __future__ import annotations

import hashlib
import html
import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.sef.company_profile import (
    CompanyProfileBuildRequest,
    CompanyProfileField,
    CompanyProfileV1,
    CriticalGapAssessment,
    ProfileEvidenceItem,
    ProfileFieldStatus,
    ProfileSectionCode,
    build_company_profile_from_request,
)
from app.sef.ledger import LedgerRequest
from app.sef.models import (
    Digest,
    Identifier,
    ReviewDecisionValue,
    SefBundle,
)
from app.sef.release_control import (
    ExecutionIntegrityState,
    IdentityResolutionState,
    MissionReleaseControl,
    SufficiencyLevel,
    release_control_blockers,
)


REPORT_SCHEMA_VERSION = "1.1.0"


class ReportModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReportReviewPackageRequest(ReportModel):
    bundle: SefBundle
    ledger_request: LedgerRequest
    entity_id: Identifier
    release_control: MissionReleaseControl


class HumanReviewInput(ReportModel):
    reviewer_ref: Identifier
    decision: ReviewDecisionValue
    reason: str = Field(min_length=1, max_length=2000)
    decided_at: datetime
    attested: bool
    reviewed_profile_digest: Digest
    reviewed_evidence_appendix_digest: Digest
    reviewed_release_control_digest: Digest

    @model_validator(mode="after")
    def decided_at_is_timezone_aware(self) -> HumanReviewInput:
        if self.decided_at.tzinfo is None or self.decided_at.utcoffset() is None:
            raise ValueError("human review decided_at must be timezone-aware")
        return self


class ReportBuildRequest(ReportReviewPackageRequest):
    review: HumanReviewInput
    generated_at: datetime
    title: str = Field(min_length=1, max_length=500)
    version: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def generated_at_is_timezone_aware(self) -> ReportBuildRequest:
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("report generated_at must be timezone-aware")
        return self


class ReportReviewPackage(ReportModel):
    schema_version: Literal["1.1.0"] = REPORT_SCHEMA_VERSION
    profile: CompanyProfileV1
    profile_digest: Digest
    evidence_appendix_digest: Digest
    release_control: MissionReleaseControl
    release_control_digest: Digest
    reviewable: bool
    blockers: list[str] = Field(default_factory=list)


class HumanSignOff(ReportModel):
    reviewer_ref: Identifier
    decision: Literal["approved"]
    reason: str = Field(min_length=1, max_length=2000)
    decided_at: datetime
    attested: Literal[True]
    reviewed_profile_digest: Digest
    reviewed_evidence_appendix_digest: Digest
    reviewed_release_control_digest: Digest
    sign_off_digest: Digest


class ReportSection(ReportModel):
    code: ProfileSectionCode
    title: str
    fields: list[CompanyProfileField] = Field(default_factory=list)


class ReportIntegrity(ReportModel):
    canonicalization: Literal["json-sort-keys-utf8-v1"] = "json-sort-keys-utf8-v1"
    profile_digest: Digest
    evidence_appendix_digest: Digest
    release_control_digest: Digest
    sign_off_digest: Digest
    report_content_digest: Digest


class ReportReleaseSummary(ReportModel):
    profile_gate_passed: Literal[True] = True
    human_review_approved: Literal[True] = True
    review_bound_to_snapshot: Literal[True] = True
    client_release_ready: Literal[True] = True
    target_sufficiency: SufficiencyLevel
    achieved_sufficiency: SufficiencyLevel
    identity_state: IdentityResolutionState
    execution_integrity: ExecutionIntegrityState
    profile_completeness: float = Field(ge=0, le=1)
    evidence_quality: float = Field(ge=0, le=1)
    commercial_priority: int = Field(ge=0, le=100)
    released_claims: int = Field(ge=1)
    evidence_items: int = Field(ge=1)
    closed_critical_gaps: int = Field(ge=6, le=6)


class HumanReviewedReportV1(ReportModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "$id": "https://aimeton.ru/schemas/sef-human-reviewed-report-v1.schema.json",
            "$schema": "https://json-schema.org/draft/2020-12/schema",
        },
    )

    schema_version: Literal["1.1.0"] = REPORT_SCHEMA_VERSION
    id: Identifier
    version: int = Field(ge=1)
    mission_id: Identifier
    entity_id: Identifier
    correlation_id: Identifier
    profile_id: Identifier
    title: str
    canonical_name: str
    as_of: datetime
    generated_at: datetime
    claim_ids: list[Identifier] = Field(min_length=1)
    sections: list[ReportSection] = Field(min_length=14, max_length=14)
    critical_gap_assessments: list[CriticalGapAssessment] = Field(
        min_length=6,
        max_length=6,
    )
    evidence_appendix: list[ProfileEvidenceItem] = Field(min_length=1)
    human_sign_off: HumanSignOff
    integrity: ReportIntegrity
    summary: ReportReleaseSummary


class ReportApiContract(ReportModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "$id": "https://aimeton.ru/schemas/sef-report-v1.schema.json",
            "$schema": "https://json-schema.org/draft/2020-12/schema",
        },
    )

    review_package_request: ReportReviewPackageRequest
    review_package: ReportReviewPackage
    report_build_request: ReportBuildRequest
    report: HumanReviewedReportV1


class ReportReleaseError(ValueError):
    def __init__(self, blockers: list[str]):
        self.blockers = sorted(set(blockers))
        super().__init__("report release blocked: " + ", ".join(self.blockers))


def _json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def canonical_digest(value: Any) -> str:
    payload = json.dumps(
        _json_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def build_review_package(
    profile: CompanyProfileV1,
    release_control: MissionReleaseControl,
) -> ReportReviewPackage:
    blockers = release_control_blockers(
        release_control,
        mission_id=profile.mission_id,
    )
    if not profile.summary.profile_gate_passed:
        blockers.append("company_profile_gate_not_passed")
    if profile.summary.hypothesis_fields:
        blockers.append("profile_contains_hypothesis")
    if profile.summary.blocked_fields:
        blockers.append("profile_contains_blocked_or_not_found")
    if not profile.evidence_appendix:
        blockers.append("evidence_appendix_empty")
    return ReportReviewPackage(
        profile=profile,
        profile_digest=canonical_digest(profile),
        evidence_appendix_digest=canonical_digest(profile.evidence_appendix),
        release_control=release_control,
        release_control_digest=canonical_digest(release_control),
        reviewable=not blockers,
        blockers=sorted(blockers),
    )


def build_review_package_from_request(
    request: ReportReviewPackageRequest,
) -> ReportReviewPackage:
    profile = build_company_profile_from_request(
        CompanyProfileBuildRequest(
            bundle=request.bundle,
            ledger_request=request.ledger_request,
            entity_id=request.entity_id,
        )
    )
    return build_review_package(profile, request.release_control)


def _release_blockers(
    request: ReportBuildRequest,
    package: ReportReviewPackage,
) -> list[str]:
    blockers = list(package.blockers)
    review = request.review
    profile = package.profile
    if review.decision != ReviewDecisionValue.APPROVED:
        blockers.append("human_review_not_approved")
    if not review.attested:
        blockers.append("human_attestation_missing")
    if review.reviewed_profile_digest != package.profile_digest:
        blockers.append("review_profile_digest_mismatch")
    if (
        review.reviewed_evidence_appendix_digest
        != package.evidence_appendix_digest
    ):
        blockers.append("review_evidence_appendix_digest_mismatch")
    if (
        review.reviewed_release_control_digest
        != package.release_control_digest
    ):
        blockers.append("review_release_control_digest_mismatch")
    if request.generated_at < profile.as_of:
        blockers.append("report_generated_before_profile_snapshot")
    if review.decided_at < profile.as_of:
        blockers.append("human_review_predates_profile_snapshot")
    if review.decided_at > request.generated_at:
        blockers.append("human_review_after_report_generation")
    return sorted(set(blockers))


def _client_sections(
    profile: CompanyProfileV1,
) -> tuple[list[ReportSection], list[str]]:
    sections: list[ReportSection] = []
    claim_ids: list[str] = []
    for section in profile.sections:
        fields = [
            field
            for field in section.fields
            if field.client_eligible
            and field.status == ProfileFieldStatus.VERIFIED
        ]
        claim_ids.extend(field.claim_id for field in fields)
        sections.append(
            ReportSection(
                code=section.code,
                title=section.title,
                fields=fields,
            )
        )
    return sections, sorted(set(claim_ids))


def _client_evidence_appendix(
    profile: CompanyProfileV1,
    claim_ids: list[str],
) -> list[ProfileEvidenceItem]:
    allowed = set(claim_ids)
    result: list[ProfileEvidenceItem] = []
    for item in profile.evidence_appendix:
        assessments = [
            assessment
            for assessment in item.claim_assessments
            if assessment.claim_id in allowed
        ]
        if assessments:
            result.append(item.model_copy(update={"claim_assessments": assessments}))
    return result


def build_human_reviewed_report(
    request: ReportBuildRequest,
) -> HumanReviewedReportV1:
    package = build_review_package_from_request(request)
    blockers = _release_blockers(request, package)
    if blockers:
        raise ReportReleaseError(blockers)

    profile = package.profile
    sections, claim_ids = _client_sections(profile)
    appendix = _client_evidence_appendix(profile, claim_ids)
    if not claim_ids:
        raise ReportReleaseError(["report_has_no_client_eligible_claims"])
    if not appendix:
        raise ReportReleaseError(["report_has_no_client_eligible_evidence"])

    sign_off_payload = {
        "reviewer_ref": request.review.reviewer_ref,
        "decision": request.review.decision.value,
        "reason": request.review.reason,
        "decided_at": request.review.decided_at.isoformat(),
        "attested": request.review.attested,
        "reviewed_profile_digest": request.review.reviewed_profile_digest,
        "reviewed_evidence_appendix_digest": (
            request.review.reviewed_evidence_appendix_digest
        ),
        "reviewed_release_control_digest": (
            request.review.reviewed_release_control_digest
        ),
    }
    sign_off_digest = canonical_digest(sign_off_payload)
    sign_off = HumanSignOff(
        **sign_off_payload,
        sign_off_digest=sign_off_digest,
    )

    content = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "version": request.version,
        "mission_id": profile.mission_id,
        "entity_id": profile.entity_id,
        "correlation_id": profile.correlation_id,
        "profile_id": profile.id,
        "title": request.title,
        "canonical_name": profile.canonical_name,
        "as_of": profile.as_of.isoformat(),
        "generated_at": request.generated_at.isoformat(),
        "claim_ids": claim_ids,
        "sections": [item.model_dump(mode="json") for item in sections],
        "critical_gap_assessments": [
            item.model_dump(mode="json")
            for item in profile.critical_gap_assessments
        ],
        "evidence_appendix": [
            item.model_dump(mode="json") for item in appendix
        ],
        "human_sign_off": sign_off.model_dump(mode="json"),
        "release_control": package.release_control.model_dump(mode="json"),
    }
    report_content_digest = canonical_digest(content)
    report_id = f"report_{report_content_digest.removeprefix('sha256:')[:24]}"

    return HumanReviewedReportV1(
        id=report_id,
        version=request.version,
        mission_id=profile.mission_id,
        entity_id=profile.entity_id,
        correlation_id=profile.correlation_id,
        profile_id=profile.id,
        title=request.title,
        canonical_name=profile.canonical_name,
        as_of=profile.as_of,
        generated_at=request.generated_at,
        claim_ids=claim_ids,
        sections=sections,
        critical_gap_assessments=profile.critical_gap_assessments,
        evidence_appendix=appendix,
        human_sign_off=sign_off,
        integrity=ReportIntegrity(
            profile_digest=package.profile_digest,
            evidence_appendix_digest=package.evidence_appendix_digest,
            release_control_digest=package.release_control_digest,
            sign_off_digest=sign_off_digest,
            report_content_digest=report_content_digest,
        ),
        summary=ReportReleaseSummary(
            target_sufficiency=package.release_control.target_sufficiency,
            achieved_sufficiency=package.release_control.achieved_sufficiency,
            identity_state=package.release_control.identity_state,
            execution_integrity=package.release_control.execution_integrity,
            profile_completeness=package.release_control.profile_completeness,
            evidence_quality=package.release_control.evidence_quality,
            commercial_priority=package.release_control.commercial_priority,
            released_claims=len(claim_ids),
            evidence_items=len(appendix),
            closed_critical_gaps=sum(
                item.closed for item in profile.critical_gap_assessments
            ),
        ),
    )


def _render_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if value is None:
        return "—"
    return str(value)


def render_report_html(report: HumanReviewedReportV1) -> str:
    section_html: list[str] = []
    for section in report.sections:
        rows = "".join(
            "<tr>"
            f"<td>{html.escape(field.predicate)}</td>"
            f"<td>{html.escape(_render_value(field.value))}</td>"
            f"<td>{html.escape(field.period or '—')}</td>"
            f"<td><code>{html.escape(field.claim_id)}</code></td>"
            "</tr>"
            for field in section.fields
        )
        if not rows:
            rows = '<tr><td colspan="4">Проверенных данных для выпуска нет.</td></tr>'
        section_html.append(
            f"<section><h2>{html.escape(section.title)}</h2>"
            "<table><thead><tr><th>Показатель</th><th>Значение</th>"
            "<th>Период</th><th>Claim</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></section>"
        )

    evidence_html = "".join(
        "<article class=\"evidence\">"
        f"<h3>{html.escape(item.document_title)}</h3>"
        f"<p><strong>Источник:</strong> {html.escape(item.publisher)} — "
        f"<a href=\"{html.escape(str(item.document_url), quote=True)}\">"
        f"{html.escape(str(item.document_url))}</a></p>"
        f"<blockquote>{html.escape(item.quote)}</blockquote>"
        f"<p><strong>Locator:</strong> {html.escape(item.locator)}</p>"
        f"<p><strong>Document digest:</strong> <code>{html.escape(item.document_digest)}</code></p>"
        f"<p><strong>Evidence digest:</strong> <code>{html.escape(item.evidence_digest)}</code></p>"
        "</article>"
        for item in report.evidence_appendix
    )

    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(report.title)}</title>
<style>
body {{ font-family: Arial, sans-serif; color: #172033; margin: 32px auto; max-width: 1100px; line-height: 1.45; }}
h1, h2, h3 {{ color: #102a43; }}
.meta, .signoff, .integrity {{ background: #f4f7fa; border-left: 4px solid #2f6fed; padding: 16px; margin: 18px 0; }}
table {{ border-collapse: collapse; width: 100%; margin-bottom: 24px; }}
th, td {{ border: 1px solid #cbd5e1; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #eaf0f7; }}
blockquote {{ border-left: 3px solid #94a3b8; margin-left: 0; padding-left: 14px; }}
code {{ overflow-wrap: anywhere; }}
.evidence {{ break-inside: avoid; border-top: 1px solid #cbd5e1; padding-top: 8px; }}
@media print {{ body {{ margin: 12mm; }} a {{ color: inherit; }} }}
</style>
</head>
<body>
<h1>{html.escape(report.title)}</h1>
<div class="meta">
<p><strong>Компания:</strong> {html.escape(report.canonical_name)}</p>
<p><strong>Версия:</strong> {report.version}; <strong>Report ID:</strong> <code>{html.escape(report.id)}</code></p>
<p><strong>Snapshot:</strong> {html.escape(report.as_of.isoformat())}; <strong>Сформирован:</strong> {html.escape(report.generated_at.isoformat())}</p>
<p><strong>УДП:</strong> {html.escape(report.summary.achieved_sufficiency.value)} / target {html.escape(report.summary.target_sufficiency.value)}</p>
<p><strong>Идентичность:</strong> {html.escape(report.summary.identity_state.value)}; <strong>исполнение:</strong> {html.escape(report.summary.execution_integrity.value)}</p>
<p><strong>Полнота профиля:</strong> {report.summary.profile_completeness:.0%}; <strong>качество evidence:</strong> {report.summary.evidence_quality:.0%}; <strong>коммерческий приоритет:</strong> {report.summary.commercial_priority}/100</p>
</div>
{''.join(section_html)}
<section>
<h2>Приложение доказательств</h2>
{evidence_html}
</section>
<div class="signoff">
<h2>Human sign-off</h2>
<p><strong>Проверил:</strong> {html.escape(report.human_sign_off.reviewer_ref)}</p>
<p><strong>Решение:</strong> approved; <strong>Время:</strong> {html.escape(report.human_sign_off.decided_at.isoformat())}</p>
<p><strong>Основание:</strong> {html.escape(report.human_sign_off.reason)}</p>
<p><strong>Sign-off digest:</strong> <code>{html.escape(report.human_sign_off.sign_off_digest)}</code></p>
</div>
<div class="integrity">
<h2>Контроль целостности</h2>
<p><strong>Profile:</strong> <code>{html.escape(report.integrity.profile_digest)}</code></p>
<p><strong>Evidence appendix:</strong> <code>{html.escape(report.integrity.evidence_appendix_digest)}</code></p>
<p><strong>Release control:</strong> <code>{html.escape(report.integrity.release_control_digest)}</code></p>
<p><strong>Report:</strong> <code>{html.escape(report.integrity.report_content_digest)}</code></p>
</div>
</body>
</html>
"""
