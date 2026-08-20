from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, Field

from app.verifier_contract import (
    CandidateVerificationScore,
    VerificationRequest,
    VerificationResult,
)


LLM_VERIFIER_FORK = "Dimar4713/llm-as-a-verifier"
# This exact engine revision passed the full AIMETON fork P0 regression suite.
LLM_VERIFIER_PINNED_SHA = "9cabf17e3644778893666b864aec924e740006ba"


class LLMVerifierSelectionEnvelope(BaseModel):
    """Normalized output from the concrete fork integration boundary.

    The live engine bridge must validate score-token evidence before producing
    this envelope.  Site Auditor does not import upstream/fork result classes.
    """

    engine: Literal["llm-verifier"] = "llm-verifier"
    engine_revision: str = Field(min_length=40, max_length=40)
    ranking_indices: list[int] = Field(min_length=1)
    scores: list[float] = Field(min_length=1)
    signal_status: Literal["valid", "missing", "degraded"]


def _request_digest(request: VerificationRequest) -> str:
    payload = json.dumps(
        request.model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def adapt_llm_verifier_selection(
    request: VerificationRequest,
    envelope: LLMVerifierSelectionEnvelope,
) -> VerificationResult:
    """Map a pinned, score-signal-validated engine result into Site Auditor.

    Fail closed on revision drift, invalid/missing score evidence, malformed
    ranking, or candidate-count mismatch.  No result produced here can grant
    client release eligibility or override hard/evidence/policy gates.
    """
    digest = _request_digest(request)

    if envelope.engine_revision != LLM_VERIFIER_PINNED_SHA:
        return VerificationResult(
            request_id=request.request_id,
            status="blocked",
            reason_code="adapter_failure",
            verifier_engine=envelope.engine,
            verifier_revision=envelope.engine_revision,
            input_digest=digest,
            metadata={"expected_revision": LLM_VERIFIER_PINNED_SHA, "revision_mismatch": True},
        )

    if envelope.signal_status != "valid":
        return VerificationResult(
            request_id=request.request_id,
            status="degraded" if envelope.signal_status == "degraded" else "blocked",
            reason_code="missing_score_evidence",
            verifier_engine=envelope.engine,
            verifier_revision=envelope.engine_revision,
            input_digest=digest,
            metadata={"signal_status": envelope.signal_status},
        )

    candidate_count = len(request.candidates)
    expected_indices = set(range(candidate_count))
    if len(envelope.scores) != candidate_count or set(envelope.ranking_indices) != expected_indices:
        return VerificationResult(
            request_id=request.request_id,
            status="blocked",
            reason_code="adapter_failure",
            verifier_engine=envelope.engine,
            verifier_revision=envelope.engine_revision,
            input_digest=digest,
            metadata={"malformed_selection": True},
        )

    ranking = [request.candidates[index].id for index in envelope.ranking_indices]
    scores = [
        CandidateVerificationScore(
            candidate_id=candidate.id,
            score=envelope.scores[index],
            signal_status="valid",
        )
        for index, candidate in enumerate(request.candidates)
    ]

    return VerificationResult(
        request_id=request.request_id,
        status="measured",
        reason_code="measured",
        ranking=ranking,
        scores=scores,
        verifier_engine=envelope.engine,
        verifier_revision=envelope.engine_revision,
        input_digest=digest,
        metadata={"fork": LLM_VERIFIER_FORK},
    )
