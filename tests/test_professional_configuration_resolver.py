from copy import deepcopy

import pytest
from jsonschema import ValidationError

from app.models import HuntRequest
from app.professional_configuration import (
    build_hunter_professional_configuration,
    normalize_professional_configuration,
    professional_configuration_digest,
    validate_professional_configuration,
)


def _build(**overrides):
    req = HuntRequest(
        region="Красноярск",
        search_zone="Красноярский край",
        industries=["Стоматология", "Медицина"],
        focus=["B2B", "частные клиники"],
        max_queries=20,
        results_per_query=10,
        max_candidates=100,
        minimum_pre_score=35,
        deep_audit_score=60,
        output_limit=25,
        concurrency=4,
    )
    kwargs = dict(
        mission_id="mission-001",
        mission_brief_revision="brief-v1",
        requested_intent="auto",
        effective_regime="precision",
        research_depth="working",
        admin_search_policy_version="admin-search-v1",
        quality_policy_version="quality-v1",
        entitlement_version="entitlement-v1",
        created_by="user:test",
        created_at="2026-08-16T13:30:00Z",
        max_cost_rub=1.0,
        max_duration_seconds=300,
        max_provider_calls=40,
    )
    kwargs.update(overrides)
    return build_hunter_professional_configuration(req, **kwargs)


def test_real_hunter_request_compiles_to_schema_valid_professional_snapshot():
    config = _build()

    validate_professional_configuration(config)
    assert config["mission_binding"] == {
        "mission_id": "mission-001",
        "mission_brief_revision": "brief-v1",
    }
    assert config["strategy"] == {
        "requested_intent": "auto",
        "effective_regime": "precision",
        "research_depth": "working",
    }
    assert [stage["id"] for stage in config["stages"]] == ["discover", "qualify", "select"]
    assert config["refinement_policy"]["allowed_actions"] == ["continue", "refine", "skip"]
    assert config["provenance"]["source_layer"] == "professional"


def test_normalization_is_deterministic_for_semantic_sets():
    first = _build()
    second = deepcopy(first)
    second["target"]["geographies"].reverse()
    second["target"]["industries"].reverse()
    second["evidence_policy"]["targets"].reverse()
    second["refinement_policy"]["allowed_actions"].reverse()

    assert normalize_professional_configuration(first) == normalize_professional_configuration(second)
    assert professional_configuration_digest(first) == professional_configuration_digest(second)


def test_execution_order_is_not_rewritten_by_normalizer():
    config = _build()
    reordered = deepcopy(config)
    reordered["stages"] = list(reversed(reordered["stages"]))

    normalized = normalize_professional_configuration(reordered)
    assert [stage["id"] for stage in normalized["stages"]] == ["select", "qualify", "discover"]
    assert professional_configuration_digest(config) != professional_configuration_digest(reordered)


def test_unknown_execution_field_fails_closed():
    config = _build()
    config["strategy"]["magic_provider_override"] = True

    with pytest.raises(ValidationError):
        validate_professional_configuration(config)


def test_historical_stop_action_is_rejected_in_favor_of_canonical_skip():
    config = _build()
    config["refinement_policy"]["allowed_actions"] = ["continue", "refine", "stop"]

    with pytest.raises(ValidationError):
        validate_professional_configuration(config)


def test_invalid_datetime_provenance_fails_with_format_checker():
    config = _build(created_at="not-a-date")

    # Builder validates before returning, so malformed provenance fails immediately.
    with pytest.raises(ValidationError):
        build_hunter_professional_configuration(
            HuntRequest(region="Красноярск"),
            mission_id="mission-001",
            mission_brief_revision="brief-v1",
            requested_intent="auto",
            effective_regime="balanced",
            research_depth="working",
            admin_search_policy_version="admin-v1",
            quality_policy_version="quality-v1",
            entitlement_version="entitlement-v1",
            created_by="user:test",
            created_at="not-a-date",
            max_cost_rub=0.0,
            max_duration_seconds=120,
            max_provider_calls=20,
        )
