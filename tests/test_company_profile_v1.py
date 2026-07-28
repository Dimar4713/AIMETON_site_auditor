from __future__ import annotations

import copy
import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from app.main import app
from app.sef.company_profile import (
    CriticalGapCode,
    CriticalGapStatus,
    ProfileFieldStatus,
    ProfileSectionCode,
    build_company_profile,
)
from app.sef.ledger import LedgerRequest, build_ledger_snapshot
from app.sef.models import SefBundle
from scripts.export_sef_company_profile_schema import TARGET, render_schema


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "sef" / "positive-chain-v0.1.json"


def _digest(seed: int) -> str:
    return f"sha256:{seed:064x}"


def _base_payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _metadata(evidence_id: str, seed: int) -> dict:
    return {
        "id": f"evidence_meta_{seed}",
        "mission_id": "mission_golden_01",
        "evidence_id": evidence_id,
        "correlation_id": "corr_golden_01",
        "tier": "tier_2_first_party",
        "valid_at": "2026-07-01T00:00:00Z",
        "fresh_until": "2027-07-01T00:00:00Z",
        "recorded_at": "2026-07-28T10:05:00Z",
    }


def _complete_payload() -> tuple[dict, list[dict]]:
    payload = _base_payload()
    metadata = [_metadata("evidence_golden_01", 1)]
    specs = [
        ("email", "info@example.ru", "contact", 10),
        ("headcount", 125, "workforce", 20),
        (
            "revenue",
            {"amount": "120000000", "currency": "RUB", "period": "2025"},
            "finance",
            30,
        ),
        ("beneficial_owner", "Иванов Иван Иванович", "ownership", 40),
        ("affiliate", "ООО «Связанная компания»", "affiliation", 50),
        (
            "legal_events_summary",
            "Проверены арбитраж, взыскания и банкротство за 2025–2026 годы",
            "legal",
            60,
        ),
    ]
    for predicate, value, source_label, seed in specs:
        source_id = f"source_{seed}"
        document_id = f"document_{seed}"
        evidence_id = f"evidence_{seed}"
        claim_id = f"claim_{seed}"
        payload["sources"].append(
            {
                "id": source_id,
                "mission_id": "mission_golden_01",
                "correlation_id": "corr_golden_01",
                "kind": "official_registry" if source_label in {"finance", "legal"} else "first_party",
                "publisher": f"Проверяемый источник {source_label}",
                "homepage_url": f"https://example.ru/{source_label}",
                "terms_ref": None,
            }
        )
        payload["documents"].append(
            {
                "id": document_id,
                "mission_id": "mission_golden_01",
                "source_id": source_id,
                "correlation_id": "corr_golden_01",
                "url": f"https://example.ru/{source_label}/document",
                "title": f"Документ {source_label}",
                "accessed_at": "2026-07-28T10:02:00Z",
                "fetch_status": "fetched",
                "content_digest": _digest(seed),
                "media_type": "text/html",
            }
        )
        payload["evidence"].append(
            {
                "id": evidence_id,
                "mission_id": "mission_golden_01",
                "source_id": source_id,
                "document_id": document_id,
                "correlation_id": "corr_golden_01",
                "evidence_type": "document_quote",
                "quote": f"Проверяемое значение {predicate}: {value}",
                "locator": f"section/{predicate}",
                "observed_at": "2026-07-28T10:03:00Z",
                "digest": _digest(seed + 1),
            }
        )
        payload["claims"].append(
            {
                "id": claim_id,
                "mission_id": "mission_golden_01",
                "entity_id": "entity_golden_01",
                "correlation_id": "corr_golden_01",
                "predicate": predicate,
                "value": value,
                "state": "confirmed",
                "critical": True,
                "evidence_refs": [
                    {"evidence_id": evidence_id, "relation": "supports"}
                ],
                "created_at": "2026-07-28T10:03:30Z",
            }
        )
        payload["review_decisions"].append(
            {
                "id": f"review_{seed}",
                "mission_id": "mission_golden_01",
                "correlation_id": "corr_golden_01",
                "target_type": "claim",
                "target_id": claim_id,
                "decision": "approved",
                "reviewer_ref": "reviewer_human_01",
                "reason": "Документ и значение проверены оператором.",
                "decided_at": "2026-07-28T10:04:00Z",
            }
        )
        metadata.append(_metadata(evidence_id, seed))
    return payload, metadata


def _snapshot(payload: dict, metadata: list[dict]):
    bundle = SefBundle.model_validate(payload)
    ledger_request = LedgerRequest.model_validate(
        {
            "mission_id": "mission_golden_01",
            "as_of": "2026-07-28T12:00:00Z",
            "evidence_metadata": metadata,
        }
    )
    return bundle, ledger_request, build_ledger_snapshot(bundle, ledger_request)


def _profile(payload: dict | None = None, metadata: list[dict] | None = None):
    if payload is None or metadata is None:
        payload, metadata = _complete_payload()
    bundle, _, ledger = _snapshot(payload, metadata)
    return bundle, ledger, build_company_profile(bundle, ledger, "entity_golden_01")


def test_company_profile_schema_is_current_and_valid():
    assert TARGET.read_text(encoding="utf-8") == render_schema()
    schema = json.loads(TARGET.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    assert schema["$id"].endswith("/sef-company-profile-v0.1.schema.json")


def test_complete_profile_closes_six_gaps_with_evidence():
    _, _, profile = _profile()

    assert len(profile.sections) == 14
    assert [item.code for item in profile.sections] == list(ProfileSectionCode)
    assert len(profile.critical_gap_assessments) == 6
    assert all(item.status == CriticalGapStatus.CLOSED for item in profile.critical_gap_assessments)
    assert profile.summary.closed_critical_gaps == 6
    assert profile.summary.critical_gap_coverage == 1.0
    assert profile.summary.profile_gate_passed is True
    assert profile.summary.client_release_ready is False
    assert profile.summary.release_blockers == [
        "human_review_and_signed_report_required"
    ]
    assert len(profile.evidence_appendix) == 7
    assert all(item.quote and item.locator for item in profile.evidence_appendix)
    assert all(item.document_digest.startswith("sha256:") for item in profile.evidence_appendix)


def test_profile_is_deterministic_and_does_not_mutate_inputs():
    payload, metadata = _complete_payload()
    bundle, _, ledger = _snapshot(payload, metadata)
    before_bundle = bundle.model_dump(mode="json")
    before_ledger = ledger.model_dump(mode="json")

    first = build_company_profile(bundle, ledger, "entity_golden_01")
    second = build_company_profile(bundle, ledger, "entity_golden_01")

    assert first == second
    assert first.id == second.id
    assert bundle.model_dump(mode="json") == before_bundle
    assert ledger.model_dump(mode="json") == before_ledger


def test_search_snippet_never_enters_profile_or_evidence_appendix():
    payload, metadata = _complete_payload()
    secret_snippet = "SEARCH_SNIPPET_MUST_NOT_BECOME_EVIDENCE"
    payload["discovery_hints"][0]["snippet"] = secret_snippet
    _, _, profile = _profile(payload, metadata)

    rendered = profile.model_dump_json()
    assert secret_snippet not in rendered
    assert payload["evidence"][0]["quote"] in rendered


def test_hypothesis_does_not_close_affiliation_gap():
    payload, metadata = _complete_payload()
    claim = next(item for item in payload["claims"] if item["predicate"] == "affiliate")
    claim["state"] = "candidate"
    payload["review_decisions"] = [
        item for item in payload["review_decisions"] if item["target_id"] != claim["id"]
    ]
    _, _, profile = _profile(payload, metadata)

    field = next(
        item
        for section in profile.sections
        for item in section.fields
        if item.claim_id == claim["id"]
    )
    gap = next(
        item
        for item in profile.critical_gap_assessments
        if item.code == CriticalGapCode.AFFILIATIONS
    )
    assert field.status == ProfileFieldStatus.HYPOTHESIS
    assert field.client_eligible is False
    assert gap.status == CriticalGapStatus.HYPOTHESIS
    assert gap.closed is False
    assert profile.summary.client_release_ready is False


def test_financial_claim_without_period_is_blocked_by_profile_gate():
    payload, metadata = _complete_payload()
    claim = next(item for item in payload["claims"] if item["predicate"] == "revenue")
    claim["value"].pop("period")
    _, ledger, profile = _profile(payload, metadata)

    assert next(item for item in ledger.claims if item.claim_id == claim["id"]).client_eligible
    field = next(
        item
        for section in profile.sections
        for item in section.fields
        if item.claim_id == claim["id"]
    )
    gap = next(
        item
        for item in profile.critical_gap_assessments
        if item.code == CriticalGapCode.FINANCIALS
    )
    assert field.status == ProfileFieldStatus.BLOCKED
    assert "financial_period_missing" in field.reason_codes
    assert gap.closed is False


def test_not_found_claim_is_visible_but_does_not_close_workforce_gap():
    payload, metadata = _complete_payload()
    claim = next(item for item in payload["claims"] if item["predicate"] == "headcount")
    evidence_id = claim["evidence_refs"][0]["evidence_id"]
    claim["state"] = "not_found"
    claim["evidence_refs"] = []
    payload["review_decisions"] = [
        item for item in payload["review_decisions"] if item["target_id"] != claim["id"]
    ]
    metadata = [item for item in metadata if item["evidence_id"] != evidence_id]
    _, _, profile = _profile(payload, metadata)

    field = next(
        item
        for section in profile.sections
        for item in section.fields
        if item.claim_id == claim["id"]
    )
    gap = next(
        item
        for item in profile.critical_gap_assessments
        if item.code == CriticalGapCode.WORKFORCE
    )
    assert field.status == ProfileFieldStatus.NOT_FOUND
    assert gap.status == CriticalGapStatus.BLOCKED
    assert gap.closed is False


def test_unresolved_conflict_blocks_contact_gap():
    payload, metadata = _complete_payload()
    original = next(item for item in payload["claims"] if item["predicate"] == "email")
    conflicting = copy.deepcopy(original)
    conflicting["id"] = "claim_contact_conflict"
    conflicting["value"] = "other@example.ru"
    payload["claims"].append(conflicting)
    _, ledger, profile = _profile(payload, metadata)

    assert ledger.summary.unresolved_conflict_groups == 1
    gap = next(
        item
        for item in profile.critical_gap_assessments
        if item.code == CriticalGapCode.CONTACTS
    )
    assert gap.status == CriticalGapStatus.BLOCKED
    assert "unresolved_conflict" in gap.reason_codes
    assert profile.summary.unresolved_conflicts == 1
    assert profile.summary.client_release_ready is False


def test_company_profile_api_returns_machine_readable_contract():
    payload, metadata = _complete_payload()
    bundle, ledger_request, _ = _snapshot(payload, metadata)
    response = TestClient(app).post(
        "/api/sef/company-profile",
        json={
            "bundle": bundle.model_dump(mode="json"),
            "ledger_request": ledger_request.model_dump(mode="json"),
            "entity_id": "entity_golden_01",
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["schema_version"] == "0.1.0"
    assert result["summary"]["closed_critical_gaps"] == 6
    assert len(result["sections"]) == 14


def test_company_profile_rejects_ledger_mission_correlation_mismatch():
    bundle, ledger, _ = _profile()
    broken = ledger.model_copy(update={"correlation_id": "corr_other"})

    try:
        build_company_profile(bundle, broken, "entity_golden_01")
    except ValueError as exc:
        assert "correlation_id" in str(exc)
    else:
        raise AssertionError("correlation mismatch must fail closed")
