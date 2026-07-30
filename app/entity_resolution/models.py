from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

from app.mission_orchestrator.models import (
    ActionCandidate,
    ActionOutcome,
    NextActionPlan,
    SufficiencyFeedback,
)
from app.sef.models import Digest, Identifier


class IdentityModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IdentityResolutionState(StrEnum):
    PROVISIONAL = "provisional"
    CONFLICTING = "conflicting"
    UNRESOLVED = "unresolved"


class IdentityCandidateState(StrEnum):
    PROVISIONAL = "provisional"
    COMPETING = "competing"


class SignalValidationState(StrEnum):
    VALID = "valid"
    INVALID = "invalid"


class IdentitySignalRef(IdentityModel):
    kind: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=500)
    normalized_value: str = Field(min_length=1, max_length=500)
    validation_state: SignalValidationState
    validation_reason: str | None = Field(default=None, max_length=200)
    document_id: Identifier
    source_url: AnyHttpUrl
    locator: str = Field(min_length=1, max_length=1_000)
    accessed_at: datetime
    document_digest: Digest


class CandidateIdentifier(IdentityModel):
    scheme: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=500)
    normalized_value: str = Field(min_length=1, max_length=500)
    signal_refs: list[IdentitySignalRef] = Field(min_length=1)
    lifecycle_state: str = "candidate"


class IdentityCandidate(IdentityModel):
    id: Identifier
    entity_type: str = Field(min_length=1, max_length=100)
    canonical_name: str = Field(min_length=1, max_length=500)
    confidence: float = Field(ge=0, le=0.99)
    state: IdentityCandidateState
    identifiers: list[CandidateIdentifier] = Field(default_factory=list)
    supporting_document_ids: list[Identifier] = Field(default_factory=list)
    accepted_identifier_links: list[Identifier] = Field(default_factory=list)


class IdentityConflict(IdentityModel):
    id: Identifier
    code: str = Field(min_length=1, max_length=200)
    candidate_ids: list[Identifier] = Field(default_factory=list)
    document_ids: list[Identifier] = Field(default_factory=list)
    detail: str = Field(min_length=1, max_length=2_000)
    requires_human_review: bool = True


class IdentityResolutionResult(IdentityModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "$id": "https://aimeton.ru/schemas/identity-resolution-v0.1.schema.json",
            "$schema": "https://json-schema.org/draft/2020-12/schema",
        },
    )

    schema_version: str = "0.1.0"
    id: Identifier
    mission_id: Identifier
    analysis_id: Identifier
    correlation_id: Identifier
    revision_number: int = Field(ge=1)
    supersedes_result_id: Identifier | None = None
    input_digest: Digest
    created_at: datetime
    plan: NextActionPlan
    state: IdentityResolutionState
    selected_candidate_id: Identifier | None = None
    candidates: list[IdentityCandidate] = Field(default_factory=list)
    conflicts: list[IdentityConflict] = Field(default_factory=list)
    invalid_signals: list[IdentitySignalRef] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    outcome: ActionOutcome
    recommended_feedback: SufficiencyFeedback
    next_action_candidates: list[ActionCandidate] = Field(default_factory=list)


class IdentityResolutionHistory(IdentityModel):
    mission_id: Identifier
    revisions: list[IdentityResolutionResult] = Field(default_factory=list)
