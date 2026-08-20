from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class VerificationCriterion(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)


class VerificationCandidate(BaseModel):
    id: str = Field(min_length=1)
    payload: dict[str, Any]


class VerificationRequest(BaseModel):
    """Provider-neutral request for semantic verification.

    The domain contract intentionally does not expose llm-verifier classes or
    provider-specific fields.  A concrete adapter may map this request to any
    verifier engine later.
    """

    schema_version: Literal["1.0"] = "1.0"
    request_id: str = Field(min_length=1)
    task: str = Field(min_length=1)
    candidates: list[VerificationCandidate] = Field(min_length=2)
    criteria: list[VerificationCriterion] = Field(min_length=1)
    evidence_digest: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    # Semantic verification never receives authority to release a client result.
    client_release_authority: Literal[False] = False


class CandidateVerificationScore(BaseModel):
    candidate_id: str = Field(min_length=1)
    score: float = Field(ge=0, le=1)
    criterion_scores: dict[str, float] = Field(default_factory=dict)
    signal_status: Literal["valid", "missing", "degraded"]


class VerificationResult(BaseModel):
    """Provider-neutral semantic-verifier result.

    `client_release_eligible` and `hard_gate_override` are literal false by
    contract.  The result is telemetry/advisory evidence only.
    """

    schema_version: Literal["1.0"] = "1.0"
    request_id: str = Field(min_length=1)
    status: Literal["measured", "blocked", "degraded"]
    reason_code: Literal[
        "measured",
        "missing_score_evidence",
        "backend_incapable",
        "adapter_failure",
    ]
    ranking: list[str] = Field(default_factory=list)
    scores: list[CandidateVerificationScore] = Field(default_factory=list)
    verifier_engine: str = Field(min_length=1)
    verifier_revision: str = Field(min_length=1)
    input_digest: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    client_release_eligible: Literal[False] = False
    hard_gate_override: Literal[False] = False


SEF_VERIFIER_CRITERIA = [
    VerificationCriterion(
        id="factual_correctness",
        name="Factual correctness",
        description="Prefer claims that match the frozen benchmark facts; penalize contradictions.",
    ),
    VerificationCriterion(
        id="evidence_grounding",
        name="Evidence grounding",
        description="Prefer claims backed by explicit accepted source provenance; unsupported claims are worse.",
    ),
    VerificationCriterion(
        id="completeness",
        name="Completeness",
        description="Prefer coverage of all required benchmark fact types without inventing missing facts.",
    ),
    VerificationCriterion(
        id="inference_discipline",
        name="Inference discipline",
        description="Prefer explicit uncertainty and conflict states over unsupported confident inference.",
    ),
]
