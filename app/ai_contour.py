from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal

from pydantic import BaseModel, ValidationError


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


def run_schema_bound_step(
    responses: Iterable[object],
    *,
    schema: type[BaseModel],
    evidence_digest: str,
    max_attempts: int = 2,
) -> AiStepResult:
    """Validate a bounded sequence of AI responses without invoking a provider.

    The caller owns response acquisition. This boundary only validates structured
    output, records sanitized attempt metadata, preserves the accepted evidence
    digest, and remains fail-closed for client release.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    attempts: list[AiAttempt] = []
    iterator = iter(responses)

    for attempt_number in range(1, max_attempts + 1):
        try:
            raw_response = next(iterator)
        except StopIteration:
            attempts.append(
                AiAttempt(
                    attempt=attempt_number,
                    accepted=False,
                    reason_code="ai_failure",
                )
            )
            return AiStepResult(
                status="degraded",
                reason_code="ai_failure",
                attempts=attempts,
                evidence_digest_before=evidence_digest,
                evidence_digest_after=evidence_digest,
            )
        except Exception:
            attempts.append(
                AiAttempt(
                    attempt=attempt_number,
                    accepted=False,
                    reason_code="ai_failure",
                )
            )
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
            attempts.append(
                AiAttempt(
                    attempt=attempt_number,
                    accepted=False,
                    reason_code="schema_validation_failed",
                )
            )
            continue

        attempts.append(
            AiAttempt(
                attempt=attempt_number,
                accepted=True,
                reason_code="accepted",
            )
        )
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
