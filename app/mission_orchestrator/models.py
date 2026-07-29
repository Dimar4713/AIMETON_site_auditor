from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class OrchestratorModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EntryPoint(StrEnum):
    UI = "ui"
    REST = "rest"
    MCP = "mcp"
    LEGACY_ADAPTER = "legacy_adapter"


class MissionLifecycle(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    DEGRADED = "degraded"
    BLOCKED = "blocked"
    COMPLETED = "completed"


class SufficiencyLevel(StrEnum):
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"
    L5 = "L5"


class QuestionState(StrEnum):
    VERIFIED = "verified"
    PARTIALLY_VERIFIED = "partially_verified"
    CONFLICTING = "conflicting"
    NOT_FOUND_AFTER_SUFFICIENT_SEARCH = "not_found_after_sufficient_search"
    NOT_SEARCHED = "not_searched"
    BLOCKED = "blocked"
    DEGRADED = "degraded"


class ActionType(StrEnum):
    CRAWL_URL = "crawl_url"
    FETCH_DOCUMENT = "fetch_document"
    QUERY_PROVIDER = "query_provider"
    RESOLVE_IDENTITY = "resolve_identity"
    REVIEW_CONFLICT = "review_conflict"
    STOP = "stop"


class StopReason(StrEnum):
    SUFFICIENCY_REACHED = "sufficiency_reached"
    SOURCE_SPACE_EXHAUSTED = "source_space_exhausted"
    BUDGET_EXHAUSTED = "budget_exhausted"
    CRITICAL_SOURCE_BLOCKED = "critical_source_blocked"
    IDENTITY_UNRESOLVED = "identity_unresolved"
    UNRESOLVED_CONFLICT = "unresolved_conflict"
    TECHNICAL_FAILURE = "technical_failure"
    POLICY_NO_ADMISSIBLE_ACTION = "policy_no_admissible_action"
    INVALID_COMPLETION = "invalid_completion"


class ActionOutcomeState(StrEnum):
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    BLOCKED = "blocked"


class MissionQuestion(OrchestratorModel):
    code: str = Field(min_length=1, max_length=100)
    required: bool = True
    critical: bool = True
    freshness_days: int | None = Field(default=None, ge=0, le=3650)


class MissionBudget(OrchestratorModel):
    max_cost_by_currency: dict[str, Decimal] = Field(default_factory=dict)
    max_actions: int = Field(default=20, ge=1, le=10_000)
    deadline_at: datetime | None = None

    @field_validator("max_cost_by_currency")
    @classmethod
    def valid_cost_limits(cls, value: dict[str, Decimal]) -> dict[str, Decimal]:
        return _validate_money_map(value)

    @field_validator("deadline_at")
    @classmethod
    def aware_deadline(cls, value: datetime | None) -> datetime | None:
        return _validate_aware_datetime(value)


class MissionCreateRequest(OrchestratorModel):
    target_url: AnyHttpUrl
    goal: str = Field(min_length=1, max_length=2_000)
    target_sufficiency: SufficiencyLevel = SufficiencyLevel.L4
    questions: list[MissionQuestion] = Field(min_length=1)
    budget: MissionBudget = Field(default_factory=MissionBudget)
    analysis_id: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def unique_question_codes(self) -> MissionCreateRequest:
        codes = [item.code for item in self.questions]
        if len(codes) != len(set(codes)):
            raise ValueError("mission question codes must be unique")
        return self


class MissionContract(OrchestratorModel):
    schema_version: str = "0.1.0"
    mission_id: str
    analysis_id: str
    correlation_id: str
    entry_point: EntryPoint
    target_url: AnyHttpUrl
    goal: str
    target_sufficiency: SufficiencyLevel
    questions: list[MissionQuestion]
    budget: MissionBudget
    contract_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    created_at: datetime


class SufficiencyFeedback(OrchestratorModel):
    achieved: SufficiencyLevel = SufficiencyLevel.L0
    question_states: dict[str, QuestionState]
    critical_gaps: list[str] = Field(default_factory=list)
    stop_reason: StopReason | None = None


class ActionCandidate(OrchestratorModel):
    action_type: ActionType
    target: str = Field(default="", max_length=4_000)
    deficit_code: str = Field(default="", max_length=200)
    expected_sufficiency_gain: float = Field(default=0, ge=0, le=1)
    ai_priority: float = Field(default=0, ge=0, le=1)
    estimated_cost_by_currency: dict[str, Decimal] = Field(default_factory=dict)
    estimated_latency_ms: int = Field(default=0, ge=0)
    error_risk: float = Field(default=0, ge=0, le=1)
    robots_allowed: bool = True
    ssrf_validated: bool = True
    rights_allowed: bool = True
    rate_limit_allowed: bool = True

    @field_validator("estimated_cost_by_currency")
    @classmethod
    def valid_estimated_cost(
        cls,
        value: dict[str, Decimal],
    ) -> dict[str, Decimal]:
        return _validate_money_map(value)


class PolicySnapshot(OrchestratorModel):
    allowed_action_types: frozenset[ActionType] = Field(
        default_factory=lambda: frozenset(ActionType)
    )
    allowed_hosts: frozenset[str] = Field(default_factory=frozenset)
    remaining_cost_by_currency: dict[str, Decimal] = Field(default_factory=dict)
    remaining_actions: int = Field(default=20, ge=0)
    deadline_at: datetime | None = None

    @field_validator("remaining_cost_by_currency")
    @classmethod
    def valid_remaining_cost(
        cls,
        value: dict[str, Decimal],
    ) -> dict[str, Decimal]:
        return _validate_money_map(value)

    @field_validator("deadline_at")
    @classmethod
    def aware_deadline(cls, value: datetime | None) -> datetime | None:
        return _validate_aware_datetime(value)


class ActionDecision(OrchestratorModel):
    candidate: ActionCandidate
    admissible: bool
    reason_codes: list[str] = Field(default_factory=list)


class NextActionPlan(OrchestratorModel):
    mission_id: str
    turn_number: int = Field(ge=1)
    input_deficits: list[str]
    decisions: list[ActionDecision]
    selected_action: ActionCandidate
    selection_reason: str


class ActionOutcome(OrchestratorModel):
    state: ActionOutcomeState
    artifact_refs: list[str] = Field(default_factory=list)
    actual_cost_by_currency: dict[str, Decimal] = Field(default_factory=dict)
    reason_codes: list[str] = Field(default_factory=list)

    @field_validator("actual_cost_by_currency")
    @classmethod
    def valid_actual_cost(
        cls,
        value: dict[str, Decimal],
    ) -> dict[str, Decimal]:
        return _validate_money_map(value)


class TurnTrace(OrchestratorModel):
    mission_id: str
    turn_number: int
    before_sufficiency: SufficiencyLevel
    input_deficits: list[str]
    decisions: list[ActionDecision]
    selected_action: ActionCandidate
    outcome: ActionOutcome
    after_sufficiency: SufficiencyLevel
    resulting_gaps: list[str]
    recorded_at: datetime


class MissionSnapshot(OrchestratorModel):
    contract: MissionContract
    lifecycle: MissionLifecycle
    achieved_sufficiency: SufficiencyLevel = SufficiencyLevel.L0
    question_states: dict[str, QuestionState]
    artifact_refs: list[str] = Field(default_factory=list)
    turns: list[TurnTrace] = Field(default_factory=list)
    stop_reason: StopReason | None = None


def _validate_money_map(value: dict[str, Decimal]) -> dict[str, Decimal]:
    if any(not currency.strip() for currency in value):
        raise ValueError("currency code must not be blank")
    if any(amount < 0 for amount in value.values()):
        raise ValueError("money amounts must be non-negative")
    return value


def _validate_aware_datetime(value: datetime | None) -> datetime | None:
    if value is not None and (
        value.tzinfo is None or value.utcoffset() is None
    ):
        raise ValueError("deadline_at must be timezone-aware")
    return value
