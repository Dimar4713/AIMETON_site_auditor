from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from .audit_contract import (
    AuditFinding,
    AuditObservation,
    NotVerified,
    QuickAuditResult,
    RejectedCandidate,
)
from .evidence_contract import InterfaceEvidenceManifest
from .rule_pack import LoadedRulePack, load_rule_pack

_SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1}
_BLOCKING_AUTHORITIES = {"standard", "aimeton_policy"}


def _rule_index(rule_pack: LoadedRulePack) -> dict[str, dict]:
    return {rule["rule_id"]: rule for rule in rule_pack.rules}


def run_quick_audit(
    manifest: InterfaceEvidenceManifest,
    observations: Iterable[AuditObservation],
    *,
    infrastructure_error: str | None = None,
    finding_cap: int = 5,
) -> QuickAuditResult:
    if not 1 <= finding_cap <= 5:
        raise ValueError("finding_cap must be between 1 and 5")

    manifest.validate()
    rule_pack = load_rule_pack()
    if manifest.rule_pack_version != rule_pack.version or manifest.rule_pack_digest != rule_pack.digest:
        raise ValueError("evidence manifest rule-pack binding does not match active rule pack")

    if infrastructure_error:
        result = QuickAuditResult(
            verdict="inconclusive",
            rule_pack_version=rule_pack.version,
            rule_pack_digest=rule_pack.digest,
            findings=(),
            considered_rejected=(),
            not_verified=(),
            infrastructure_error=infrastructure_error[:500],
        )
        result.validate()
        return result

    rules = _rule_index(rule_pack)
    evidence_refs = {artifact.ref for artifact in manifest.artifacts}
    rejected: list[RejectedCandidate] = []
    not_verified: list[NotVerified] = []
    grouped: dict[tuple[str, str, str], list[AuditObservation]] = defaultdict(list)

    for observation in observations:
        observation.validate()
        rule = rules.get(observation.rule_id)
        if rule is None:
            raise ValueError(f"unknown rule_id: {observation.rule_id}")
        if not observation.confirmed:
            rejected.append(
                RejectedCandidate(
                    rule_id=observation.rule_id,
                    summary=observation.summary,
                    reason=observation.rejection_reason or "not confirmed",
                )
            )
            continue
        if not observation.evidence_ref or observation.evidence_ref not in evidence_refs:
            not_verified.append(
                NotVerified(
                    rule_id=observation.rule_id,
                    summary=observation.summary,
                    reason="missing or unknown evidence reference",
                )
            )
            continue
        if not observation.locator:
            not_verified.append(
                NotVerified(
                    rule_id=observation.rule_id,
                    summary=observation.summary,
                    reason="missing reproducible locator",
                )
            )
            continue
        grouped[(observation.rule_id, observation.evidence_ref, observation.locator)].append(observation)

    findings: list[AuditFinding] = []
    for (rule_id, evidence_ref, locator), items in grouped.items():
        rule = rules[rule_id]
        best = max(items, key=lambda item: (item.user_impact, item.reach, item.summary))
        findings.append(
            AuditFinding(
                rule_id=rule_id,
                rule_version=rule["rule_version"],
                domain=rule["domain"],
                authority=rule["authority"],
                severity=rule["severity"],
                evidence_ref=evidence_ref,
                locator=locator,
                summary=best.summary,
                user_impact=max(item.user_impact for item in items),
                reach=max(item.reach for item in items),
                occurrence_count=len(items),
            )
        )

    findings.sort(
        key=lambda finding: (
            -_SEVERITY_RANK[finding.severity],
            -finding.user_impact,
            -finding.reach,
            finding.rule_id,
            finding.locator,
        )
    )
    selected = tuple(findings[:finding_cap])

    if any(
        finding.severity == "high" and finding.authority in _BLOCKING_AUTHORITIES
        for finding in selected
    ):
        verdict = "block"
    elif selected:
        verdict = "needs_changes"
    else:
        verdict = "approve"

    result = QuickAuditResult(
        verdict=verdict,
        rule_pack_version=rule_pack.version,
        rule_pack_digest=rule_pack.digest,
        findings=selected,
        considered_rejected=tuple(sorted(rejected, key=lambda item: (item.rule_id, item.summary))),
        not_verified=tuple(sorted(not_verified, key=lambda item: (item.rule_id, item.summary))),
    )
    result.validate()
    return result
