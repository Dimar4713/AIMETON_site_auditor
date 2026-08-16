import copy
import json
from pathlib import Path

import jsonschema
import pytest


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "config" / "professional_configuration.schema.json"


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _valid_configuration() -> dict:
    return {
        "schema_version": "0.1",
        "recipe_ref": {
            "recipe_id": "regional-target-hunt",
            "recipe_version": "1",
        },
        "mission_binding": {
            "mission_id": "mission-123",
            "mission_brief_revision": "3",
        },
        "target": {
            "geographies": ["Красноярск"],
            "industries": ["Стоматология"],
            "entity_types": ["company"],
            "include": [],
            "exclude": [],
        },
        "strategy": {
            "requested_intent": "auto",
            "effective_regime": "precision",
            "research_depth": "working",
        },
        "stages": [
            {
                "id": "discovery",
                "capability": "company_discovery",
                "enabled": True,
                "depends_on": [],
                "provider_roles": ["regional_search", "open_web_search"],
                "parameters": {},
            }
        ],
        "evidence_policy": {
            "targets": ["region", "industry", "direct_or_official"],
            "minimum_direct_sources": 1,
            "require_provenance": True,
            "sufficiency_rule": None,
        },
        "refinement_policy": {
            "mode": "shadow",
            "max_additional_waves": 1,
            "allowed_actions": ["continue", "refine", "skip"],
        },
        "interaction_policy": {
            "consultation_enabled": True,
            "checkpoints": [
                "before_material_scope_expansion",
                "after_intermediate_result",
            ],
            "material_scope_change_requires_preview": True,
        },
        "output_contract": {
            "format": "shortlist",
            "max_results": 50,
            "sections": ["company", "reason", "evidence"],
            "sort_by": "quality",
            "group_by": None,
        },
        "resource_envelope": {
            "max_cost_rub": 1.0,
            "max_duration_seconds": 300,
            "max_provider_calls": 100,
        },
        "policy_refs": {
            "admin_search_policy_version": "stage-current",
            "quality_policy_version": "stage-current",
            "entitlement_version": "product-dev",
        },
        "provenance": {
            "created_by": "test",
            "created_at": "2026-08-15T00:00:00Z",
            "source_layer": "professional",
            "source_preset_version": None,
            "source_guided_profile_version": None,
        },
    }


def test_professional_configuration_schema_is_valid_json_schema() -> None:
    jsonschema.Draft202012Validator.check_schema(_schema())


def test_representative_professional_configuration_validates() -> None:
    jsonschema.Draft202012Validator(_schema()).validate(_valid_configuration())


def test_unknown_execution_significant_field_fails_closed() -> None:
    configuration = _valid_configuration()
    configuration["strategy"]["secret_new_routing_switch"] = True

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(_schema()).validate(configuration)


def test_mission_binding_is_required() -> None:
    configuration = _valid_configuration()
    del configuration["mission_binding"]

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(_schema()).validate(configuration)


def test_run_provenance_source_layer_is_bounded() -> None:
    configuration = _valid_configuration()
    configuration["provenance"]["source_layer"] = "parallel-secret-backend"

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(_schema()).validate(configuration)


def test_same_semantics_can_be_attributed_to_each_arrow_layer() -> None:
    validator = jsonschema.Draft202012Validator(_schema())
    baseline = _valid_configuration()

    for layer in ("professional", "guided", "preset"):
        configuration = copy.deepcopy(baseline)
        configuration["provenance"]["source_layer"] = layer
        if layer == "guided":
            configuration["provenance"]["source_guided_profile_version"] = "guided-1"
        if layer == "preset":
            configuration["provenance"]["source_preset_version"] = "preset-1"
        validator.validate(configuration)
