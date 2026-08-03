from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError


class AiAttempt(BaseModel):
    attempt: int
    accepted: bool
    reason_code: Literal["accepted", "schema_validation_failed", "ai_failure"]


class AiStepResult(BaseModel):
    status: Literal["accepted", "blocked", "degraded"]
    reason_code: Literal["accepted", "schema_validation_failed", "ai_failure"]
    attempts: list[AiAttempt]
    value: dict[str, Any] | None = None
    evidence_digest_before: str
    evidence_digest_after: str
    client_release_eligible: Literal[False] = False


class SourceBoundFact(BaseModel):
    field: str
    value: str
    source_ids: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    provenance_status: Literal["accepted_evidence", "preliminary_hypothesis"]


class SourceBoundFactsResult(BaseModel):
    status: Literal["accepted", "blocked"]
    reason_code: Literal["accepted", "unknown_source", "heuristic_not_verified"]
    facts: list[SourceBoundFact]
    evidence_digest: str
    model: str
    schema_version: str
    input_digest: str
    client_release_eligible: bool


class SynthesisClaim(BaseModel):
    claim: str
    source_ids: list[str] = Field(min_length=1)
    entity_ids: list[str] = Field(default_factory=list)


class SourceBoundSynthesisResult(BaseModel):
    status: Literal["accepted", "blocked"]
    reason_code: Literal["accepted", "unsupported_claim", "unsupported_source", "unsupported_entity"]
    claims: list[SynthesisClaim]
    evidence_digest: str
    model: str
    schema_version: str
    input_digest: str
    client_release_eligible: bool


def run_schema_bound_step(
    responses: Iterable[object],
    *,
    schema: type[BaseModel],
    evidence_digest: str,
    max_attempts: int = 2,
) -> AiStepResult:
    """Validate a bounded sequence of AI responses without invoking a provider."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    attempts: list[AiAttempt] = []
    iterator = iter(responses)

    for attempt_number in range(1, max_attempts + 1):
        try:
            raw_response = next(iterator)
        except StopIteration:
            attempts.append(AiAttempt(attempt=attempt_number, accepted=False, reason_code="ai_failure"))
            return AiStepResult(
                status="degraded",
                reason_code="ai_failure",
                attempts=attempts,
                evidence_digest_before=evidence_digest,
                evidence_digest_after=evidence_digest,
            )
        except Exception:
            attempts.append(AiAttempt(attempt=attempt_number, accepted=False, reason_code="ai_failure"))
            return AiStepResult(
                status="degraded",
                reason_code="ai_failure",
                attempts=attempts,
                evidence_digest_before=evidence_digest,
                evidence_digest_after=evidence_digest,
            )

        try:
            validated = schema.model_validate(raw_response)
        except ValidationError:
            attempts.append(AiAttempt(attempt=attempt_number, accepted=False, reason_code="schema_validation_failed"))
            continue

        attempts.append(AiAttempt(attempt=attempt_number, accepted=True, reason_code="accepted"))
        return AiStepResult(
            status="accepted",
            reason_code="accepted",
            attempts=attempts,
            value=validated.model_dump(mode="json"),
            evidence_digest_before=evidence_digest,
            evidence_digest_after=evidence_digest,
        )

    return AiStepResult(
        status="blocked",
        reason_code="schema_validation_failed",
        attempts=attempts,
        evidence_digest_before=evidence_digest,
        evidence_digest_after=evidence_digest,
    )


def validate_source_bound_facts(
    facts: Iterable[SourceBoundFact | dict[str, Any]],
    *,
    allowed_source_ids: set[str],
    evidence_digest: str,
    model: str,
    schema_version: str,
    input_digest: str,
) -> SourceBoundFactsResult:
    """Reject invented provenance and keep heuristic claims preliminary."""
    validated = [SourceBoundFact.model_validate(fact) for fact in facts]
    validated.sort(key=lambda fact: (fact.field, fact.value, tuple(sorted(fact.source_ids))))

    if any(set(fact.source_ids) - allowed_source_ids for fact in validated):
        return SourceBoundFactsResult(
            status="blocked",
            reason_code="unknown_source",
            facts=validated,
            evidence_digest=evidence_digest,
            model=model,
            schema_version=schema_version,
            input_digest=input_digest,
            client_release_eligible=False,
        )

    has_preliminary = any(fact.provenance_status == "preliminary_hypothesis" for fact in validated)
    return SourceBoundFactsResult(
        status="accepted" if not has_preliminary else "blocked",
        reason_code="accepted" if not has_preliminary else "heuristic_not_verified",
        facts=validated,
        evidence_digest=evidence_digest,
        model=model,
        schema_version=schema_version,
        input_digest=input_digest,
        client_release_eligible=not has_preliminary,
    )


def validate_source_bound_synthesis(
    claims: Iterable[SynthesisClaim | dict[str, Any]],
    *,
    allowed_claims: set[str],
    allowed_source_ids: set[str],
    allowed_entity_ids: set[str],
    evidence_digest: str,
    model: str,
    schema_version: str,
    input_digest: str,
) -> SourceBoundSynthesisResult:
    """Accept synthesis only when every claim, source and entity exists in the accepted snapshot."""
    validated = [SynthesisClaim.model_validate(claim) for claim in claims]
    validated.sort(key=lambda item: (item.claim, tuple(sorted(item.source_ids)), tuple(sorted(item.entity_ids))))

    reason_code: Literal["accepted", "unsupported_claim", "unsupported_source", "unsupported_entity"] = "accepted"
    if any(item.claim not in allowed_claims for item in validated):
        reason_code = "unsupported_claim"
    elif any(set(item.source_ids) - allowed_source_ids for item in validated):
        reason_code = "unsupported_source"
    elif any(set(item.entity_ids) - allowed_entity_ids for item in validated):
        reason_code = "unsupported_entity"

    accepted = reason_code == "accepted"
    return SourceBoundSynthesisResult(
        status="accepted" if accepted else "blocked",
        reason_code=reason_code,
        claims=validated,
        evidence_digest=evidence_digest,
        model=model,
        schema_version=schema_version,
        input_digest=input_digest,
        client_release_eligible=accepted,
    )
