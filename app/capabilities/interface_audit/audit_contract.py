from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Verdict = Literal["block", "needs_changes", "approve", "inconclusive"]


@dataclass(frozen=True)
class AuditObservation:
    rule_id: str
    evidence_ref: str | None
    locator: str | None
    summary: str
    user_impact: int = 1
    reach: int = 1
    confirmed: bool = True
    rejection_reason: str | None = None

    def validate(self) -> None:
        if not self.rule_id.strip():
            raise ValueError("observation rule_id is required")
        if not self.summary.strip():
            raise ValueError("observation summary is required")
        if not 1 <= self.user_impact <= 5:
            raise ValueError("user_impact must be between 1 and 5")
        if not 1 <= self.reach <= 5:
            raise ValueError("reach must be between 1 and 5")
        if not self.confirmed and not self.rejection_reason:
            raise ValueError("rejected observation requires rejection_reason")


@dataclass(frozen=True)
class AuditFinding:
    rule_id: str
    rule_version: str
    domain: str
    authority: str
    severity: str
    evidence_ref: str
    locator: str
    summary: str
    user_impact: int
    reach: int
    occurrence_count: int


@dataclass(frozen=True)
class RejectedCandidate:
    rule_id: str
    summary: str
    reason: str


@dataclass(frozen=True)
class NotVerified:
    rule_id: str
    summary: str
    reason: str


@dataclass(frozen=True)
class QuickAuditResult:
    verdict: Verdict
    rule_pack_version: str
    rule_pack_digest: str
    findings: tuple[AuditFinding, ...]
    considered_rejected: tuple[RejectedCandidate, ...]
    not_verified: tuple[NotVerified, ...]
    infrastructure_error: str | None = None

    def validate(self) -> None:
        if self.verdict not in {"block", "needs_changes", "approve", "inconclusive"}:
            raise ValueError("unsupported verdict")
        if not self.rule_pack_version or len(self.rule_pack_digest) != 64:
            raise ValueError("exact rule-pack version and digest are required")
        if len(self.findings) > 5:
            raise ValueError("quick audit finding cap exceeded")
        if self.verdict == "inconclusive" and not self.infrastructure_error:
            raise ValueError("inconclusive verdict requires infrastructure_error")
        if self.verdict != "inconclusive" and self.infrastructure_error:
            raise ValueError("infrastructure_error is only valid for inconclusive verdict")
        for finding in self.findings:
            if not finding.evidence_ref or not finding.locator:
                raise ValueError("every finding requires evidence_ref and locator")
