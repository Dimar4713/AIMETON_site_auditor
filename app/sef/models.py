from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator


SEF_SCHEMA_VERSION = "0.1.0"
SchemaVersion = Literal["0.1.0"]
Identifier = Annotated[str, Field(min_length=1, max_length=200)]
CorrelationId = Annotated[str, Field(min_length=1, max_length=200)]
Digest = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
ClaimValue = str | int | float | bool | list[str] | dict[str, str] | None


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MissionState(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    REVIEW = "review"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SearchPlanState(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ClaimState(StrEnum):
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    CONTRADICTED = "contradicted"
    NOT_FOUND = "not_found"


class EvidenceRelation(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"


class SourceKind(StrEnum):
    OFFICIAL_REGISTRY = "official_registry"
    FIRST_PARTY = "first_party"
    LICENSED_PROVIDER = "licensed_provider"
    NEWS_MEDIA = "news_media"
    INDUSTRY_CATALOG = "industry_catalog"
    SCIENTIFIC_DATABASE = "scientific_database"
    SOCIAL = "social"
    MANUAL = "manual"


class ProviderCallState(StrEnum):
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class DocumentFetchState(StrEnum):
    FETCHED = "fetched"
    FAILED = "failed"
    BLOCKED = "blocked"


class ReviewDecisionValue(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"


class SearchPlan(ContractModel):
    id: Identifier
    status: SearchPlanState
    query_count: int = Field(ge=0)
    required_source_kinds: list[SourceKind] = Field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @model_validator(mode="after")
    def completed_plan_has_execution(self) -> SearchPlan:
        if self.status == SearchPlanState.COMPLETED:
            if self.query_count < 1:
                raise ValueError("completed search plan requires at least one executed query")
            if self.completed_at is None:
                raise ValueError("completed search plan requires completed_at")
        return self


class Mission(ContractModel):
    id: Identifier
    schema_version: SchemaVersion = SEF_SCHEMA_VERSION
    runtime_task_id: Identifier
    correlation_id: CorrelationId
    title: str = Field(min_length=1, max_length=300)
    goal: str = Field(min_length=1, max_length=2000)
    state: MissionState
    search_plan: SearchPlan
    created_at: datetime
    updated_at: datetime


class Entity(ContractModel):
    id: Identifier
    mission_id: Identifier
    correlation_id: CorrelationId
    entity_type: str = Field(min_length=1, max_length=100)
    canonical_name: str = Field(min_length=1, max_length=500)


class EntityIdentifier(ContractModel):
    id: Identifier
    mission_id: Identifier
    entity_id: Identifier
    correlation_id: CorrelationId
    scheme: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=1000)
    normalized_value: str = Field(min_length=1, max_length=1000)


class Source(ContractModel):
    id: Identifier
    mission_id: Identifier
    correlation_id: CorrelationId
    kind: SourceKind
    publisher: str = Field(min_length=1, max_length=500)
    homepage_url: AnyHttpUrl
    terms_ref: str | None = Field(default=None, max_length=1000)


class Document(ContractModel):
    id: Identifier
    mission_id: Identifier
    source_id: Identifier
    correlation_id: CorrelationId
    url: AnyHttpUrl
    title: str = Field(min_length=1, max_length=1000)
    accessed_at: datetime
    fetch_status: DocumentFetchState
    content_digest: Digest | None = None
    media_type: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def fetched_document_has_digest(self) -> Document:
        if self.fetch_status == DocumentFetchState.FETCHED and self.content_digest is None:
            raise ValueError("fetched document requires content_digest")
        return self


class ProviderCall(ContractModel):
    id: Identifier
    mission_id: Identifier
    correlation_id: CorrelationId
    provider_ref: Identifier
    operation: str = Field(min_length=1, max_length=200)
    request_fingerprint: Digest
    state: ProviderCallState
    started_at: datetime
    finished_at: datetime


class DiscoveryHint(ContractModel):
    id: Identifier
    mission_id: Identifier
    provider_call_id: Identifier
    correlation_id: CorrelationId
    url: AnyHttpUrl
    title: str = Field(min_length=1, max_length=1000)
    snippet: str = Field(min_length=1, max_length=4000)
    discovered_at: datetime


class Evidence(ContractModel):
    id: Identifier
    mission_id: Identifier
    source_id: Identifier
    document_id: Identifier
    correlation_id: CorrelationId
    evidence_type: Literal["document_quote", "official_record", "dataset_row"]
    quote: str = Field(min_length=1, max_length=8000)
    locator: str = Field(min_length=1, max_length=1000)
    observed_at: datetime
    digest: Digest


class ClaimEvidenceRef(ContractModel):
    evidence_id: Identifier
    relation: EvidenceRelation


class Claim(ContractModel):
    id: Identifier
    mission_id: Identifier
    entity_id: Identifier
    correlation_id: CorrelationId
    predicate: str = Field(min_length=1, max_length=300)
    value: ClaimValue
    state: ClaimState
    critical: bool = False
    evidence_refs: list[ClaimEvidenceRef] = Field(default_factory=list)
    created_at: datetime

    @model_validator(mode="after")
    def state_has_required_evidence_relation(self) -> Claim:
        relations = {item.relation for item in self.evidence_refs}
        if self.state == ClaimState.CONFIRMED and EvidenceRelation.SUPPORTS not in relations:
            raise ValueError("confirmed claim requires supporting document evidence")
        if self.state == ClaimState.CONTRADICTED and EvidenceRelation.CONTRADICTS not in relations:
            raise ValueError("contradicted claim requires contradicting document evidence")
        if self.state == ClaimState.NOT_FOUND and self.evidence_refs:
            raise ValueError("not_found claim cannot cite positive or contradictory evidence")
        return self


class CostEvent(ContractModel):
    id: Identifier
    mission_id: Identifier
    provider_call_id: Identifier | None = None
    correlation_id: CorrelationId
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    amount: Decimal = Field(ge=0, max_digits=18, decimal_places=6)
    units: Decimal = Field(ge=0, max_digits=18, decimal_places=6)
    unit_name: str = Field(min_length=1, max_length=100)
    occurred_at: datetime


class ReviewDecision(ContractModel):
    id: Identifier
    mission_id: Identifier
    correlation_id: CorrelationId
    target_type: Literal["claim", "evidence", "report"]
    target_id: Identifier
    decision: ReviewDecisionValue
    reviewer_ref: Identifier
    reason: str = Field(min_length=1, max_length=2000)
    decided_at: datetime


class Report(ContractModel):
    id: Identifier
    mission_id: Identifier
    correlation_id: CorrelationId
    title: str = Field(min_length=1, max_length=500)
    claim_ids: list[Identifier]
    client_facing: bool = True
    generated_at: datetime


class SefBundle(ContractModel):
    """Provider-neutral transport and validation envelope for SEF v0.1."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "$id": "https://aimeton.ru/schemas/sef-v0.1.schema.json",
            "$schema": "https://json-schema.org/draft/2020-12/schema",
        },
    )

    schema_version: SchemaVersion = SEF_SCHEMA_VERSION
    missions: list[Mission] = Field(min_length=1)
    entities: list[Entity] = Field(default_factory=list)
    entity_identifiers: list[EntityIdentifier] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    documents: list[Document] = Field(default_factory=list)
    provider_calls: list[ProviderCall] = Field(default_factory=list)
    discovery_hints: list[DiscoveryHint] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    cost_events: list[CostEvent] = Field(default_factory=list)
    review_decisions: list[ReviewDecision] = Field(default_factory=list)
    reports: list[Report] = Field(default_factory=list)

    @staticmethod
    def _index(records: list[ContractModel], kind: str) -> dict[str, ContractModel]:
        result: dict[str, ContractModel] = {}
        for record in records:
            record_id = getattr(record, "id")
            if record_id in result:
                raise ValueError(f"duplicate {kind} id: {record_id}")
            result[record_id] = record
        return result

    @model_validator(mode="after")
    def enforce_referential_and_evidence_invariants(self) -> SefBundle:
        missions = self._index(self.missions, "mission")
        entities = self._index(self.entities, "entity")
        sources = self._index(self.sources, "source")
        documents = self._index(self.documents, "document")
        calls = self._index(self.provider_calls, "provider_call")
        evidence = self._index(self.evidence, "evidence")
        claims = self._index(self.claims, "claim")
        reports = self._index(self.reports, "report")

        mission_scoped: list[ContractModel] = [
            *self.entities,
            *self.entity_identifiers,
            *self.sources,
            *self.documents,
            *self.provider_calls,
            *self.discovery_hints,
            *self.evidence,
            *self.claims,
            *self.cost_events,
            *self.review_decisions,
            *self.reports,
        ]
        for record in mission_scoped:
            mission = missions.get(getattr(record, "mission_id"))
            if mission is None:
                raise ValueError(f"{record.__class__.__name__} references unknown mission")
            if getattr(record, "correlation_id") != mission.correlation_id:
                raise ValueError(f"{record.__class__.__name__} breaks mission correlation_id")

        for identifier in self.entity_identifiers:
            entity = entities.get(identifier.entity_id)
            if entity is None or entity.mission_id != identifier.mission_id:
                raise ValueError("entity_identifier references an entity outside its mission")

        for document in self.documents:
            source = sources.get(document.source_id)
            if source is None or source.mission_id != document.mission_id:
                raise ValueError("document references a source outside its mission")

        for hint in self.discovery_hints:
            call = calls.get(hint.provider_call_id)
            if call is None or call.mission_id != hint.mission_id:
                raise ValueError("discovery_hint references a provider call outside its mission")

        for item in self.evidence:
            source = sources.get(item.source_id)
            document = documents.get(item.document_id)
            if source is None or document is None:
                raise ValueError("evidence requires an existing source and fetched document")
            if document.fetch_status != DocumentFetchState.FETCHED:
                raise ValueError("evidence cannot be promoted from an unfetched document")
            if document.source_id != item.source_id:
                raise ValueError("evidence source must match the document source")
            if source.mission_id != item.mission_id or document.mission_id != item.mission_id:
                raise ValueError("evidence references records outside its mission")

        for claim in self.claims:
            entity = entities.get(claim.entity_id)
            if entity is None or entity.mission_id != claim.mission_id:
                raise ValueError("claim references an entity outside its mission")
            for link in claim.evidence_refs:
                item = evidence.get(link.evidence_id)
                if item is None or item.mission_id != claim.mission_id:
                    raise ValueError("claim references evidence outside its mission")
            if claim.state == ClaimState.NOT_FOUND:
                mission = missions[claim.mission_id]
                if mission.search_plan.status != SearchPlanState.COMPLETED:
                    raise ValueError("not_found claim requires a completed search plan")

        for event in self.cost_events:
            if event.provider_call_id is not None:
                call = calls.get(event.provider_call_id)
                if call is None or call.mission_id != event.mission_id:
                    raise ValueError("cost_event references a provider call outside its mission")

        targets: dict[str, dict[str, ContractModel]] = {
            "claim": claims,
            "evidence": evidence,
            "report": reports,
        }
        for decision in self.review_decisions:
            target = targets[decision.target_type].get(decision.target_id)
            if target is None or getattr(target, "mission_id") != decision.mission_id:
                raise ValueError("review_decision target is missing or belongs to another mission")

        for report in self.reports:
            for claim_id in report.claim_ids:
                claim = claims.get(claim_id)
                if claim is None or claim.mission_id != report.mission_id:
                    raise ValueError("report references a claim outside its mission")
                if report.client_facing and claim.critical and claim.state != ClaimState.CONFIRMED:
                    raise ValueError("critical unsupported claim cannot enter a client report")

        return self
