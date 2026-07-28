from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from app.sef.models import SefBundle
from scripts.export_sef_schema import TARGET, render_schema


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "sef"
MIGRATION = ROOT / "migrations" / "sef" / "0001_sef_v0_1.sql"
GOLDEN_5 = ROOT / "benchmarks" / "sef" / "golden-5-v0.1.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def positive_payload() -> dict:
    return load_json(FIXTURES / "positive-chain-v0.1.json")


def test_committed_json_schema_is_current_and_valid():
    assert TARGET.read_text(encoding="utf-8") == render_schema()
    schema = load_json(TARGET)
    Draft202012Validator.check_schema(schema)
    assert schema["$id"] == "https://aimeton.ru/schemas/sef-v0.1.schema.json"


def test_positive_hint_document_evidence_claim_chain():
    bundle = SefBundle.model_validate(positive_payload())
    Draft202012Validator(load_json(TARGET)).validate(bundle.model_dump(mode="json"))

    assert bundle.discovery_hints[0].id == "hint_golden_01"
    assert bundle.evidence[0].document_id == bundle.documents[0].id
    assert bundle.claims[0].evidence_refs[0].evidence_id == bundle.evidence[0].id
    assert bundle.claims[0].state.value == "confirmed"


def test_search_snippet_cannot_confirm_claim():
    payload = load_json(FIXTURES / "forbidden-snippet-confirmed-v0.1.json")
    with pytest.raises(ValidationError, match="confirmed claim requires supporting document evidence"):
        SefBundle.model_validate(payload)


def test_llm_cannot_be_registered_as_source():
    payload = positive_payload()
    payload["sources"][0]["kind"] = "llm"
    with pytest.raises(ValidationError):
        SefBundle.model_validate(payload)


def test_not_found_requires_completed_executed_search_plan():
    payload = positive_payload()
    payload["claims"][0]["state"] = "not_found"
    payload["claims"][0]["evidence_refs"] = []
    payload["reports"] = []
    payload["missions"][0]["search_plan"]["status"] = "running"
    payload["missions"][0]["search_plan"]["completed_at"] = None

    with pytest.raises(ValidationError, match="not_found claim requires a completed search plan"):
        SefBundle.model_validate(payload)


def test_critical_unconfirmed_claim_is_blocked_from_client_report():
    payload = positive_payload()
    payload["claims"][0]["state"] = "candidate"
    payload["claims"][0]["evidence_refs"] = []

    with pytest.raises(
        ValidationError,
        match="critical unsupported claim cannot enter a client report",
    ):
        SefBundle.model_validate(payload)


def test_conflicting_claims_are_retained_as_separate_records():
    payload = positive_payload()
    contradictory = copy.deepcopy(payload["claims"][0])
    contradictory["id"] = "claim_golden_02"
    contradictory["value"] = "ООО «ДРУГОЕ НАЗВАНИЕ»"
    contradictory["state"] = "contradicted"
    contradictory["evidence_refs"][0]["relation"] = "contradicts"
    payload["claims"].append(contradictory)

    bundle = SefBundle.model_validate(payload)
    same_predicate = [claim for claim in bundle.claims if claim.predicate == "legal_name"]
    assert [claim.id for claim in same_predicate] == ["claim_golden_01", "claim_golden_02"]


def test_runtime_to_evidence_correlation_id_is_unbroken():
    bundle = SefBundle.model_validate(positive_payload())
    correlation_ids = {
        bundle.missions[0].correlation_id,
        bundle.provider_calls[0].correlation_id,
        bundle.evidence[0].correlation_id,
        bundle.claims[0].correlation_id,
    }
    assert correlation_ids == {"corr_golden_01"}


def test_portable_sql_migration_builds_full_sef_store(tmp_path):
    db_path = tmp_path / "sef.sqlite3"
    with sqlite3.connect(db_path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        db.executescript(MIGRATION.read_text(encoding="utf-8"))
        db.executescript(MIGRATION.read_text(encoding="utf-8"))
        tables = {
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'sef_%'"
            )
        }
        schema_version = db.execute(
            "SELECT value FROM sef_meta WHERE key = 'schema_version'"
        ).fetchone()[0]

    assert schema_version == "0.1.0"
    assert {
        "sef_missions",
        "sef_entities",
        "sef_entity_identifiers",
        "sef_sources",
        "sef_documents",
        "sef_provider_calls",
        "sef_discovery_hints",
        "sef_evidence",
        "sef_claims",
        "sef_claim_evidence",
        "sef_cost_events",
        "sef_review_decisions",
        "sef_reports",
        "sef_report_claims",
    } <= tables


def test_golden_5_is_expressible_without_provider_specific_fields():
    golden = load_json(GOLDEN_5)
    payload = {
        "schema_version": "0.1.0",
        "missions": [],
        "entities": [],
        "entity_identifiers": [],
    }
    for ordinal, case in enumerate(golden["cases"], start=1):
        case_id = case["case_id"].lower().replace("-", "_")
        legal_name = next(
            fact["value"] for fact in case["facts"] if fact["predicate"] == "legal_name"
        )
        domain = next(
            fact["value"] for fact in case["facts"] if fact["predicate"] == "official_domain"
        )
        correlation_id = f"corr_{case_id}"
        mission_id = f"mission_{case_id}"
        entity_id = f"entity_{case_id}"
        payload["missions"].append(
            {
                "id": mission_id,
                "schema_version": "0.1.0",
                "runtime_task_id": f"task_{case_id}",
                "correlation_id": correlation_id,
                "title": f"Проверка {case['case_id']}",
                "goal": "Сформировать доказательный профиль компании",
                "state": "created",
                "search_plan": {
                    "id": f"search_plan_{case_id}",
                    "status": "planned",
                    "query_count": 0,
                    "required_source_kinds": ["first_party"],
                    "started_at": None,
                    "completed_at": None,
                },
                "created_at": f"2026-07-28T10:0{ordinal}:00Z",
                "updated_at": f"2026-07-28T10:0{ordinal}:00Z",
            }
        )
        payload["entities"].append(
            {
                "id": entity_id,
                "mission_id": mission_id,
                "correlation_id": correlation_id,
                "entity_type": "company",
                "canonical_name": legal_name,
            }
        )
        payload["entity_identifiers"].append(
            {
                "id": f"identifier_{case_id}",
                "mission_id": mission_id,
                "entity_id": entity_id,
                "correlation_id": correlation_id,
                "scheme": "domain",
                "value": domain,
                "normalized_value": domain,
            }
        )

    bundle = SefBundle.model_validate(payload)
    assert len(bundle.missions) == 5
    assert len(bundle.entities) == 5
    assert bundle.provider_calls == []
    serialized = bundle.model_dump(mode="json")
    assert all("provider" not in mission for mission in serialized["missions"])
