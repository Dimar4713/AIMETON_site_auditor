from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

from app.sef.ledger import (
    ConflictState,
    EffectiveReviewState,
    EvidenceMetadata,
    EvidenceTier,
    LedgerContract,
    LedgerRequest,
    build_ledger_snapshot,
    require_client_eligible_claims,
)
from app.sef.models import SefBundle
from scripts.export_sef_ledger_schema import TARGET, render_schema


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "sef" / "positive-chain-v0.1.json"
BASE_MIGRATION = ROOT / "migrations" / "sef" / "0001_sef_v0_1.sql"
LEDGER_MIGRATION = (
    ROOT / "migrations" / "sef" / "0002_claim_evidence_ledger_v0_1.sql"
)


def load_payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def metadata(
    *,
    valid_at: str = "2026-07-01T00:00:00Z",
    fresh_until: str | None = "2026-12-31T00:00:00Z",
    tier: str = "tier_2_first_party",
) -> dict:
    return {
        "id": "evidence_meta_golden_01",
        "mission_id": "mission_golden_01",
        "evidence_id": "evidence_golden_01",
        "correlation_id": "corr_golden_01",
        "tier": tier,
        "valid_at": valid_at,
        "fresh_until": fresh_until,
        "recorded_at": "2026-07-28T10:01:06Z",
    }


def request(*, metadata_items: list[dict], as_of: str = "2026-07-28T12:00:00Z"):
    return LedgerRequest.model_validate(
        {
            "mission_id": "mission_golden_01",
            "as_of": as_of,
            "evidence_metadata": metadata_items,
            "policy": {
                "default_max_age_days": 365,
                "predicates": [
                    {
                        "predicate": "legal_name",
                        "max_age_days": 365,
                        "accepted_tiers": [
                            "tier_1_authority",
                            "tier_2_first_party",
                        ],
                    }
                ],
            },
        }
    )


def review(
    *,
    decision_id: str,
    target_id: str,
    decision: str,
    decided_at: str,
) -> dict:
    return {
        "id": decision_id,
        "mission_id": "mission_golden_01",
        "correlation_id": "corr_golden_01",
        "target_type": "claim",
        "target_id": target_id,
        "decision": decision,
        "reviewer_ref": "operator_01",
        "reason": "Ручная проверка источника и значения.",
        "decided_at": decided_at,
    }


def test_committed_ledger_schema_is_current_and_valid():
    assert TARGET.read_text(encoding="utf-8") == render_schema()
    schema = json.loads(TARGET.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    assert schema["$id"] == "https://aimeton.ru/schemas/sef-ledger-v0.1.schema.json"


def test_current_accepted_evidence_makes_confirmed_claim_client_eligible():
    bundle = SefBundle.model_validate(load_payload())
    snapshot = build_ledger_snapshot(
        bundle,
        request(metadata_items=[metadata()]),
    )

    entry = snapshot.claims[0]
    assert entry.client_eligible is True
    assert entry.reason_codes == []
    assert entry.supporting_evidence[0].tier == EvidenceTier.FIRST_PARTY
    assert snapshot.summary.critical_coverage == 1.0
    assert snapshot.summary.client_eligible_claims == 1


def test_current_critical_claim_still_requires_human_approval():
    payload = load_payload()
    payload["review_decisions"] = []
    snapshot = build_ledger_snapshot(
        SefBundle.model_validate(payload),
        request(metadata_items=[metadata()]),
    )

    assert snapshot.claims[0].client_eligible is False
    assert "critical_claim_requires_approval" in snapshot.claims[0].reason_codes
    assert snapshot.summary.pending_review_claims == 1


def test_stale_critical_evidence_requires_explicit_approval():
    payload = load_payload()
    payload["review_decisions"] = []
    bundle = SefBundle.model_validate(payload)
    stale = metadata(fresh_until="2026-07-10T00:00:00Z")
    snapshot = build_ledger_snapshot(bundle, request(metadata_items=[stale]))

    entry = snapshot.claims[0]
    assert entry.client_eligible is False
    assert "stale_evidence_requires_approval" in entry.reason_codes
    assert snapshot.summary.stale_evidence == 1
    assert snapshot.summary.pending_review_claims == 1

    payload = load_payload()
    payload["review_decisions"] = []
    payload["review_decisions"].append(
        review(
            decision_id="review_stale_approved",
            target_id="claim_golden_01",
            decision="approved",
            decided_at="2026-07-28T11:00:00Z",
        )
    )
    approved = build_ledger_snapshot(
        SefBundle.model_validate(payload),
        request(metadata_items=[stale]),
    )
    assert approved.claims[0].client_eligible is True
    assert approved.claims[0].review_state == EffectiveReviewState.APPROVED


def test_approval_before_freshness_expiry_does_not_authorize_later_stale_use():
    bundle = SefBundle.model_validate(load_payload())
    stale_after_review = metadata(fresh_until="2026-07-30T00:00:00Z")
    snapshot = build_ledger_snapshot(
        bundle,
        request(
            metadata_items=[stale_after_review],
            as_of="2026-08-01T00:00:00Z",
        ),
    )

    assert snapshot.claims[0].review_state == EffectiveReviewState.APPROVED
    assert snapshot.claims[0].client_eligible is False
    assert "stale_evidence_requires_approval" in snapshot.claims[0].reason_codes


def test_missing_or_unaccepted_evidence_metadata_fails_closed():
    bundle = SefBundle.model_validate(load_payload())
    missing = build_ledger_snapshot(bundle, request(metadata_items=[]))
    assert missing.claims[0].client_eligible is False
    assert "admissible_evidence_missing" in missing.claims[0].reason_codes

    weak = build_ledger_snapshot(
        bundle,
        request(metadata_items=[metadata(tier="tier_4_signal")]),
    )
    assert weak.claims[0].client_eligible is False
    assert "admissible_evidence_missing" in weak.claims[0].reason_codes


def test_conflicting_claims_are_grouped_and_blocked_until_human_resolution():
    payload = load_payload()
    contradictory = copy.deepcopy(payload["claims"][0])
    contradictory["id"] = "claim_golden_02"
    contradictory["value"] = "ООО «ДРУГОЕ НАЗВАНИЕ»"
    payload["claims"].append(contradictory)
    bundle = SefBundle.model_validate(payload)

    unresolved = build_ledger_snapshot(
        bundle,
        request(metadata_items=[metadata()]),
    )
    assert len(unresolved.conflicts) == 1
    assert unresolved.conflicts[0].state == ConflictState.UNRESOLVED
    assert unresolved.summary.unresolved_conflict_groups == 1
    assert all(not item.client_eligible for item in unresolved.claims)
    assert all("unresolved_conflict" in item.reason_codes for item in unresolved.claims)

    payload["review_decisions"].extend(
        [
            review(
                decision_id="review_claim_01",
                target_id="claim_golden_01",
                decision="approved",
                decided_at="2026-07-28T11:00:00Z",
            ),
            review(
                decision_id="review_claim_02",
                target_id="claim_golden_02",
                decision="rejected",
                decided_at="2026-07-28T11:01:00Z",
            ),
        ]
    )
    resolved = build_ledger_snapshot(
        SefBundle.model_validate(payload),
        request(metadata_items=[metadata()]),
    )
    assert resolved.conflicts[0].state == ConflictState.RESOLVED
    assert resolved.conflicts[0].accepted_claim_id == "claim_golden_01"
    by_id = {item.claim_id: item for item in resolved.claims}
    assert by_id["claim_golden_01"].client_eligible is True
    assert by_id["claim_golden_02"].client_eligible is False
    assert "claim_rejected" in by_id["claim_golden_02"].reason_codes


def test_latest_review_is_deterministic_and_history_is_not_mutated():
    payload = load_payload()
    initial_review_count = len(payload["review_decisions"])
    payload["review_decisions"].extend(
        [
            review(
                decision_id="review_older",
                target_id="claim_golden_01",
                decision="approved",
                decided_at="2026-07-28T10:30:00Z",
            ),
            review(
                decision_id="review_newer",
                target_id="claim_golden_01",
                decision="rejected",
                decided_at="2026-07-28T11:30:00Z",
            ),
        ]
    )
    bundle = SefBundle.model_validate(payload)
    before = bundle.model_dump(mode="json")

    snapshot = build_ledger_snapshot(
        bundle,
        request(metadata_items=[metadata()]),
    )

    assert snapshot.claims[0].review_state == EffectiveReviewState.REJECTED
    assert snapshot.claims[0].latest_review_decision_id == "review_newer"
    assert snapshot.claims[0].client_eligible is False
    assert len(bundle.review_decisions) == initial_review_count + 2
    assert bundle.model_dump(mode="json") == before


def test_decisions_created_after_snapshot_time_are_ignored():
    payload = load_payload()
    payload["review_decisions"].append(
        review(
            decision_id="review_from_future",
            target_id="claim_golden_01",
            decision="rejected",
            decided_at="2026-07-28T13:00:00Z",
        )
    )
    snapshot = build_ledger_snapshot(
        SefBundle.model_validate(payload),
        request(metadata_items=[metadata()], as_of="2026-07-28T12:00:00Z"),
    )

    assert snapshot.claims[0].review_state == EffectiveReviewState.APPROVED
    assert snapshot.claims[0].latest_review_decision_id == "review_golden_01"
    assert snapshot.claims[0].client_eligible is True


def test_client_report_gate_rejects_ineligible_and_unknown_claims():
    payload = load_payload()
    payload["review_decisions"] = []
    snapshot = build_ledger_snapshot(
        SefBundle.model_validate(payload),
        request(metadata_items=[metadata()]),
    )

    with pytest.raises(ValueError, match="critical_claim_requires_approval"):
        require_client_eligible_claims(snapshot, ["claim_golden_01"])
    with pytest.raises(ValueError, match="claim_missing_from_ledger"):
        require_client_eligible_claims(snapshot, ["claim_unknown"])


def test_ledger_contract_round_trips_through_json_schema():
    bundle = SefBundle.model_validate(load_payload())
    ledger_request = request(metadata_items=[metadata()])
    snapshot = build_ledger_snapshot(bundle, ledger_request)
    contract = LedgerContract(request=ledger_request, snapshot=snapshot)

    schema = json.loads(TARGET.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(contract.model_dump(mode="json"))


def test_portable_ledger_migration_is_repeatable(tmp_path):
    db_path = tmp_path / "sef-ledger.sqlite3"
    with sqlite3.connect(db_path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        db.executescript(BASE_MIGRATION.read_text(encoding="utf-8"))
        db.executescript(LEDGER_MIGRATION.read_text(encoding="utf-8"))
        db.executescript(LEDGER_MIGRATION.read_text(encoding="utf-8"))
        tables = {
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'sef_%'"
            )
        }

    assert {
        "sef_evidence_ledger_metadata",
        "sef_predicate_freshness_policies",
        "sef_claim_conflict_groups",
        "sef_claim_conflict_members",
        "sef_ledger_snapshots",
    } <= tables


def test_future_evidence_is_not_current():
    bundle = SefBundle.model_validate(load_payload())
    future = metadata(
        valid_at="2026-08-01T00:00:00Z",
        fresh_until="2026-12-31T00:00:00Z",
    )
    snapshot = build_ledger_snapshot(
        bundle,
        request(metadata_items=[future]),
    )

    assert snapshot.claims[0].client_eligible is False
    assert "admissible_evidence_missing" in snapshot.claims[0].reason_codes
