import pytest
from pydantic import BaseModel, Field

from app.ai_contour import run_schema_bound_step


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
    assert result.reason_code == "accepted"
    assert [attempt.reason_code for attempt in result.attempts] == [
        "schema_validation_failed",
        "accepted",
    ]
    assert result.value == {
        "field": "revenue",
        "value": "100",
        "confidence": 0.8,
    }
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
    assert result.reason_code == "schema_validation_failed"
    assert len(result.attempts) == 2
    assert all(not attempt.accepted for attempt in result.attempts)
    assert result.value is None
    assert result.client_release_eligible is False


def test_provider_or_response_exhaustion_is_typed_degradation():
    result = run_schema_bound_step(
        [],
        schema=ExtractedFact,
        evidence_digest=EVIDENCE_DIGEST,
        max_attempts=2,
    )

    assert result.status == "degraded"
    assert result.reason_code == "ai_failure"
    assert result.attempts[0].reason_code == "ai_failure"
    assert result.client_release_eligible is False


def test_ai_failure_never_changes_previously_accepted_evidence_digest():
    result = run_schema_bound_step(
        [{"field": "revenue", "value": "100", "confidence": 2}],
        schema=ExtractedFact,
        evidence_digest=EVIDENCE_DIGEST,
        max_attempts=1,
    )

    assert result.evidence_digest_before == EVIDENCE_DIGEST
    assert result.evidence_digest_after == EVIDENCE_DIGEST


def test_retry_bound_must_be_positive():
    with pytest.raises(ValueError, match="max_attempts"):
        run_schema_bound_step(
            [],
            schema=ExtractedFact,
            evidence_digest=EVIDENCE_DIGEST,
            max_attempts=0,
        )
