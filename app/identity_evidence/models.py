from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.entity_resolution.models import IdentityResolutionResult
from app.mission_orchestrator.models import (
    ActionCandidate,
    ActionOutcome,
    NextActionPlan,
    SufficiencyFeedback,
)
from app.search_gateway.models import SearchDiagnostics
from app.sef.models import (
    Digest,
    DiscoveryHint,
    Document,
    Entity,
    EntityIdentifier,
    Evidence,
    Identifier,
    ProviderCall,
    Source,
)


class IdentityEvidenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceGuardState(StrEnum):
    ACCEPTED = "accepted"
    BLOCKED = "blocked"


class IdentitySearchResult(IdentityEvidenceModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "$id": "https://aimeton.ru/schemas/identity-search-v0.1.schema.json",
            "$schema": "https://json-schema.org/draft/2020-12/schema",
        },
    )

    schema_version: str = "0.1.0"
    id: Identifier
    mission_id: Identifier
    analysis_id: Identifier
    correlation_id: Identifier
    identity_result_id: Identifier
    plan: NextActionPlan
    provider_call: ProviderCall
    discovery_hints: list[DiscoveryHint] = Field(default_factory=list)
    diagnostics: SearchDiagnostics
    outcome: ActionOutcome
    recommended_feedback: SufficiencyFeedback
    next_action_candidates: list[ActionCandidate] = Field(default_factory=list)


class AcceptedIdentifierEvidence(IdentityEvidenceModel):
    identifier: EntityIdentifier
    evidence: Evidence


class IdentityEvidenceResult(IdentityEvidenceModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "$id": "https://aimeton.ru/schemas/identity-evidence-v0.1.schema.json",
            "$schema": "https://json-schema.org/draft/2020-12/schema",
        },
    )

    schema_version: str = "0.1.0"
    id: Identifier
    mission_id: Identifier
    analysis_id: Identifier
    correlation_id: Identifier
    identity_result_id: Identifier
    identity_search_result_id: Identifier
    plan: NextActionPlan
    guard_state: EvidenceGuardState
    guard_reason_codes: list[str] = Field(default_factory=list)
    source: Source
    document: Document
    raw_content_digest: Digest
    normalized_content_digest: Digest
    entity: Entity
    accepted: list[AcceptedIdentifierEvidence] = Field(default_factory=list)
    identity_revision: IdentityResolutionResult | None = None
    outcome: ActionOutcome
    recommended_feedback: SufficiencyFeedback
    next_action_candidates: list[ActionCandidate] = Field(default_factory=list)
