from __future__ import annotations

from app.capabilities.interface_audit.audit_contract import AuditObservation
from app.capabilities.interface_audit.evidence_contract import EvidenceArtifact, InterfaceEvidenceManifest
from app.capabilities.interface_audit.quick_orchestrator import run_quick_audit
from app.capabilities.interface_audit.rule_pack import load_rule_pack


def _manifest() -> InterfaceEvidenceManifest:
    rule_pack = load_rule_pack()
    return InterfaceEvidenceManifest(
        final_url="https://example.test/",
        title="Example",
        language="en",
        viewport={"width": 320, "height": 800},
        color_scheme="light",
        reduced_motion="reduce",
        rule_pack_version=rule_pack.version,
        rule_pack_digest=rule_pack.digest,
        artifacts=(EvidenceArtifact.from_bytes("dom.html", "text/html", b"<html></html>"),),
        console_messages=(),
        page_errors=(),
        failed_requests=(),
        redirects=(),
    )


def test_high_policy_finding_blocks_and_duplicates_consolidate():
    observations = [
        AuditObservation("IA-LAYOUT-001", "dom.html", "#primary", "Primary action is clipped", 5, 5),
        AuditObservation("IA-LAYOUT-001", "dom.html", "#primary", "Button is outside viewport", 4, 5),
    ]
    result = run_quick_audit(_manifest(), observations)
    assert result.verdict == "block"
    assert len(result.findings) == 1
    assert result.findings[0].occurrence_count == 2
    assert result.findings[0].user_impact == 5


def test_missing_evidence_is_not_verified_not_finding():
    result = run_quick_audit(
        _manifest(),
        [AuditObservation("IA-WRITING-001", "missing.png", "#cta", "Technical label")],
    )
    assert result.verdict == "approve"
    assert result.findings == ()
    assert len(result.not_verified) == 1


def test_unconfirmed_candidate_is_rejected():
    result = run_quick_audit(
        _manifest(),
        [
            AuditObservation(
                "IA-WRITING-001",
                "dom.html",
                "#cta",
                "Possible unclear label",
                confirmed=False,
                rejection_reason="context makes the action clear",
            )
        ],
    )
    assert result.verdict == "approve"
    assert len(result.considered_rejected) == 1


def test_infrastructure_failure_is_inconclusive():
    result = run_quick_audit(_manifest(), [], infrastructure_error="browser unavailable")
    assert result.verdict == "inconclusive"
    assert result.infrastructure_error == "browser unavailable"


def test_finding_cap_and_deterministic_ordering():
    observations = [
        AuditObservation("IA-WRITING-001", "dom.html", f"#item-{index}", f"Finding {index}", index, index)
        for index in range(1, 6)
    ]
    result = run_quick_audit(_manifest(), observations, finding_cap=3)
    assert len(result.findings) == 3
    assert [finding.user_impact for finding in result.findings] == [5, 4, 3]
