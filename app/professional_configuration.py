from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from app.models import HuntRequest


_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "config" / "professional_configuration.schema.json"

# These arrays are semantic sets. Execution-ordered arrays such as stages and
# checkpoints are deliberately NOT sorted.
_SET_PATHS: tuple[tuple[str, ...], ...] = (
    ("target", "geographies"),
    ("target", "industries"),
    ("target", "entity_types"),
    ("evidence_policy", "targets"),
    ("refinement_policy", "allowed_actions"),
)


def load_professional_configuration_schema() -> dict[str, Any]:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def _validate_timezone_aware_iso8601(value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("provenance.created_at must be a non-empty ISO-8601 datetime")
    raw = value.strip()
    try:
        parsed = datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith("Z") else raw)
    except ValueError as exc:
        raise ValidationError("provenance.created_at must be valid ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValidationError("provenance.created_at must include a timezone offset")


def validate_professional_configuration(config: Mapping[str, Any]) -> None:
    """Fail closed against schema plus critical semantic invariants."""
    validator = Draft202012Validator(
        load_professional_configuration_schema(),
        format_checker=FormatChecker(),
    )
    payload = dict(config)
    validator.validate(payload)
    provenance = payload.get("provenance")
    if not isinstance(provenance, Mapping):
        raise ValidationError("provenance must be an object")
    _validate_timezone_aware_iso8601(provenance.get("created_at"))


def _normalize_string(value: str) -> str:
    return " ".join(value.strip().split())


def _normalize_set_at_path(config: dict[str, Any], path: tuple[str, ...]) -> None:
    cursor: Any = config
    for key in path[:-1]:
        cursor = cursor[key]
    leaf = path[-1]
    values = cursor[leaf]
    if not isinstance(values, list):
        return
    normalized = [_normalize_string(v) if isinstance(v, str) else v for v in values]
    # Schema validation happens before normalization, so duplicate input cannot
    # be silently repaired when uniqueItems=true.
    cursor[leaf] = sorted(normalized, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))


def normalize_professional_configuration(config: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deterministic, schema-valid snapshot without changing semantics."""
    validate_professional_configuration(config)
    normalized = deepcopy(dict(config))
    for path in _SET_PATHS:
        _normalize_set_at_path(normalized, path)
    validate_professional_configuration(normalized)
    return normalized


def canonical_professional_configuration_json(config: Mapping[str, Any]) -> str:
    normalized = normalize_professional_configuration(config)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def professional_configuration_digest(config: Mapping[str, Any]) -> str:
    payload = canonical_professional_configuration_json(config).encode("utf-8")
    return f"sha256:{sha256(payload).hexdigest()}"


def build_hunter_professional_configuration(
    request: HuntRequest,
    *,
    mission_id: str,
    mission_brief_revision: str,
    requested_intent: str,
    effective_regime: str,
    research_depth: str,
    admin_search_policy_version: str,
    quality_policy_version: str,
    entitlement_version: str,
    created_by: str,
    created_at: str,
    max_cost_rub: float,
    max_duration_seconds: int,
    max_provider_calls: int,
) -> dict[str, Any]:
    """Compile the existing Hunter request into the Professional Core contract.

    This adapter is intentionally execution-neutral: it does not call providers,
    change routing, or grant authorization. Policy resolution remains below this
    contract and may reject or constrain the requested configuration later.
    """
    geographies = [request.region]
    if request.search_zone:
        geographies.append(request.search_zone)

    config: dict[str, Any] = {
        "schema_version": "0.1",
        "recipe_ref": None,
        "mission_binding": {
            "mission_id": mission_id,
            "mission_brief_revision": mission_brief_revision,
        },
        "target": {
            "geographies": geographies,
            "industries": list(request.industries),
            "entity_types": ["company"],
            "include": list(request.focus),
            "exclude": [],
        },
        "strategy": {
            "requested_intent": requested_intent,
            "effective_regime": effective_regime,
            "research_depth": research_depth,
        },
        "stages": [
            {
                "id": "discover",
                "capability": "company_discovery",
                "enabled": True,
                "depends_on": [],
                "provider_roles": ["search"],
                "parameters": {
                    "max_queries": request.max_queries,
                    "results_per_query": request.results_per_query,
                    "max_candidates": request.max_candidates,
                },
            },
            {
                "id": "qualify",
                "capability": "candidate_qualification",
                "enabled": True,
                "depends_on": ["discover"],
                "provider_roles": [],
                "parameters": {
                    "minimum_pre_score": request.minimum_pre_score,
                    "deep_audit_score": request.deep_audit_score,
                },
            },
            {
                "id": "select",
                "capability": "result_selection",
                "enabled": True,
                "depends_on": ["qualify"],
                "provider_roles": [],
                "parameters": {"output_limit": request.output_limit},
            },
        ],
        "evidence_policy": {
            "targets": ["direct_source", "industry_confirmation", "region_confirmation"],
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
            "checkpoints": ["before_material_scope_change", "after_intermediate_result"],
            "material_scope_change_requires_preview": True,
        },
        "output_contract": {
            "format": "shortlist",
            "max_results": request.output_limit,
            "sections": ["candidate", "evidence", "qualification"],
            "sort_by": "qualification",
            "group_by": None,
        },
        "resource_envelope": {
            "max_cost_rub": max_cost_rub,
            "max_duration_seconds": max_duration_seconds,
            "max_provider_calls": max_provider_calls,
        },
        "policy_refs": {
            "admin_search_policy_version": admin_search_policy_version,
            "quality_policy_version": quality_policy_version,
            "entitlement_version": entitlement_version,
        },
        "provenance": {
            "created_by": created_by,
            "created_at": created_at,
            "source_layer": "professional",
            "source_preset_version": None,
            "source_guided_profile_version": None,
        },
    }
    return normalize_professional_configuration(config)
