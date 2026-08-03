import pytest
from pydantic import BaseModel, Field

from app.ai_contour import (
    SourceBoundFact,
    SynthesisClaim,
    run_schema_bound_step,
    validate_source_bound_facts,
    validate_source_bound_synthesis,
)


class ExtractedFact(BaseModel):
    field: str
    value: str
    confidence: float = Field(ge=0, le=1)


EVIDENCE_DIGEST = "sha256:" + "a" * 64


def test_invalid_response_can_be_repaired_once_within_bound():
    result = run_schema_bound_step(
        [
            {"field": "revenue", "value": "100", "confidence": 2},
            {"field": "revenue", "value": "100", "confidence": 0.8},
        ],
        schema=ExtractedFact,
        evidence_digest=EVIDENCE_DIGEST,
        max_attempts=2,
    )
    assert result.status == "accepted"
    assert [attempt.reason_code for attempt in result.attempts] == ["schema_validation_failed", "accepted"]
    assert result.client_release_eligible is False


def test_repeated_invalid_responses_stop_at_bound_and_block_release():
    result = run_schema_bound_step(
        [
            {"field": "revenue", "value": "100", "confidence": 2},
            {"field": "revenue", "value": "100", "confidence": -1},
            {"field": "revenue", "value": "100", "confidence": 0.8},
        ],
        schema=ExtractedFact,
        evidence_digest=EVIDENCE_DIGEST,
        max_attempts=2,
    )
    assert result.status == "blocked"
    assert len(result.attempts) == 2
    assert result.client_release_eligible is False


def test_provider_or_response_exhaustion_is_typed_degradation():
    result = run_schema_bound_step([], schema=ExtractedFact, evidence_digest=EVIDENCE_DIGEST, max_attempts=2)
    assert result.status == "degraded"
    assert result.reason_code == "ai_failure"


def test_ai_failure_never_changes_previously_accepted_evidence_digest():
    result = run_schema_bound_step(
        [{"field": "revenue", "value": "100", "confidence": 2}],
        schema=ExtractedFact,
        evidence_digest=EVIDENCE_DIGEST,
        max_attempts=1,
    )
    assert result.evidence_digest_before == result.evidence_digest_after == EVIDENCE_DIGEST


def test_retry_bound_must_be_positive():
    with pytest.raises(ValueError, match="max_attempts"):
        run_schema_bound_step([], schema=ExtractedFact, evidence_digest=EVIDENCE_DIGEST, max_attempts=0)


def test_unknown_source_blocks_ai_facts_and_client_release():
    result = validate_source_bound_facts(
        [SourceBoundFact(field="revenue", value="100", source_ids=["invented"], confidence=0.8, provenance_status="accepted_evidence")],
        allowed_source_ids={"doc-1"},
        evidence_digest=EVIDENCE_DIGEST,
        model="deterministic-fixture",
        schema_version="facts-v1",
        input_digest="sha256:input",
    )
    assert result.status == "blocked"
    assert result.reason_code == "unknown_source"
    assert result.client_release_eligible is False


def test_heuristic_fact_cannot_be_promoted_to_verified():
    result = validate_source_bound_facts(
        [SourceBoundFact(field="employees", value="50", source_ids=["doc-1"], confidence=0.6, provenance_status="preliminary_hypothesis")],
        allowed_source_ids={"doc-1"},
        evidence_digest=EVIDENCE_DIGEST,
        model="heuristic-v1",
        schema_version="facts-v1",
        input_digest="sha256:input",
    )
    assert result.status == "blocked"
    assert result.reason_code == "heuristic_not_verified"
    assert result.client_release_eligible is False


def test_same_snapshot_produces_stable_fact_order():
    facts = [
        SourceBoundFact(field="revenue", value="100", source_ids=["doc-2"], confidence=0.8, provenance_status="accepted_evidence"),
        SourceBoundFact(field="employees", value="50", source_ids=["doc-1"], confidence=0.9, provenance_status="accepted_evidence"),
    ]
    kwargs = dict(
        allowed_source_ids={"doc-1", "doc-2"},
        evidence_digest=EVIDENCE_DIGEST,
        model="deterministic-fixture",
        schema_version="facts-v1",
        input_digest="sha256:input",
    )
    first = validate_source_bound_facts(facts, **kwargs)
    second = validate_source_bound_facts(reversed(facts), **kwargs)
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.client_release_eligible is True


def synthesis_kwargs():
    return dict(
        allowed_claims={"Company revenue is 100"},
        allowed_source_ids={"doc-1"},
        allowed_entity_ids={"company-1"},
        evidence_digest=EVIDENCE_DIGEST,
        model="deterministic-fixture",
        schema_version="synthesis-v1",
        input_digest="sha256:input",
    )


def test_synthesis_rejects_claim_absent_from_ledger_snapshot():
    result = validate_source_bound_synthesis(
        [SynthesisClaim(claim="Company revenue is 999", source_ids=["doc-1"], entity_ids=["company-1"])],
        **synthesis_kwargs(),
    )
    assert result.status == "blocked"
    assert result.reason_code == "unsupported_claim"
    assert result.client_release_eligible is False


def test_synthesis_rejects_invented_source():
    result = validate_source_bound_synthesis(
        [SynthesisClaim(claim="Company revenue is 100", source_ids=["invented"], entity_ids=["company-1"])],
        **synthesis_kwargs(),
    )
    assert result.reason_code == "unsupported_source"
    assert result.client_release_eligible is False


def test_synthesis_rejects_invented_entity():
    result = validate_source_bound_synthesis(
        [SynthesisClaim(claim="Company revenue is 100", source_ids=["doc-1"], entity_ids=["invented"])],
        **synthesis_kwargs(),
    )
    assert result.reason_code == "unsupported_entity"
    assert result.client_release_eligible is False


def test_synthesis_accepts_only_snapshot_bound_claims():
    result = validate_source_bound_synthesis(
        [SynthesisClaim(claim="Company revenue is 100", source_ids=["doc-1"], entity_ids=["company-1"])],
        **synthesis_kwargs(),
    )
    assert result.status == "accepted"
    assert result.reason_code == "accepted"
    assert result.client_release_eligible is True
    assert result.evidence_digest == EVIDENCE_DIGEST
