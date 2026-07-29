from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.sef.models import Identifier


RELEASE_CONTROL_SCHEMA_VERSION = "0.1.0"


class ReleaseControlModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SufficiencyLevel(StrEnum):
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"
    L5 = "L5"

    @property
    def rank(self) -> int:
        return int(self.value[1:])


class ExecutionIntegrityState(StrEnum):
    VALIDATED = "validated"
    DEGRADED = "degraded"
    BLOCKED = "blocked"
    VALIDATION_ERROR = "validation_error"


class IdentityResolutionState(StrEnum):
    RESOLVED = "resolved"
    PROVISIONAL = "provisional"
    UNRESOLVED = "unresolved"
    CONFLICTING = "conflicting"


class AnalysisState(StrEnum):
    SCHEMA_VALIDATED = "schema_validated"
    PRELIMINARY_HYPOTHESIS = "preliminary_hypothesis"
    VALIDATION_ERROR = "validation_error"


class VerticalState(StrEnum):
    VERIFIED = "verified"
    PARTIALLY_VERIFIED = "partially_verified"
    CONFLICTING = "conflicting"
    NOT_FOUND_AFTER_SUFFICIENT_SEARCH = "not_found_after_sufficient_search"
    NOT_SEARCHED = "not_searched"
    BLOCKED = "blocked"
    DEGRADED = "degraded"


class ProviderReadinessState(StrEnum):
    ACTIVE = "active"
    NOT_CONFIGURED = "not_configured"
    PRICING_UNKNOWN = "pricing_unknown"
    BUDGET_BLOCKED = "budget_blocked"
    QUOTA_BLOCKED = "quota_blocked"
    CIRCUIT_OPEN = "circuit_open"
    FAILED = "failed"


class BudgetState(StrEnum):
    WITHIN_BUDGET = "within_budget"
    UNKNOWN = "unknown"
    EXHAUSTED = "exhausted"


class RequiredVerticalStatus(ReleaseControlModel):
    code: Identifier
    required: bool = True
    state: VerticalState
    reason_codes: list[str] = Field(default_factory=list)


class ProviderReadiness(ReleaseControlModel):
    provider_ref: Identifier
    required: bool = False
    state: ProviderReadinessState
    reason_codes: list[str] = Field(default_factory=list)


class MissionReleaseControl(ReleaseControlModel):
    """Fail-closed release snapshot produced by the mission runtime.

    SA-SR-00 introduces this server-owned boundary before the full Mission
    Orchestrator and sufficiency evaluator exist. Later stages populate the same
    contract; Report v1 never infers readiness from profile completeness.
    """

    schema_version: Literal["0.1.0"] = RELEASE_CONTROL_SCHEMA_VERSION
    mission_id: Identifier
    evaluated_at: datetime
    target_sufficiency: SufficiencyLevel
    achieved_sufficiency: SufficiencyLevel
    identity_state: IdentityResolutionState
    execution_integrity: ExecutionIntegrityState
    analysis_state: AnalysisState
    unresolved_critical_conflicts: int = Field(default=0, ge=0)
    required_verticals: list[RequiredVerticalStatus] = Field(min_length=1)
    providers: list[ProviderReadiness] = Field(default_factory=list)
    budget_state: BudgetState
    profile_completeness: float = Field(ge=0, le=1)
    evidence_quality: float = Field(ge=0, le=1)
    commercial_priority: int = Field(ge=0, le=100)
    reason_codes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_snapshot(self) -> MissionReleaseControl:
        if self.evaluated_at.tzinfo is None or self.evaluated_at.utcoffset() is None:
            raise ValueError("release control evaluated_at must be timezone-aware")
        vertical_codes = [item.code for item in self.required_verticals]
        if len(vertical_codes) != len(set(vertical_codes)):
            raise ValueError("release control vertical codes must be unique")
        provider_refs = [item.provider_ref for item in self.providers]
        if len(provider_refs) != len(set(provider_refs)):
            raise ValueError("release control provider refs must be unique")
        return self


def release_control_blockers(
    control: MissionReleaseControl,
    *,
    mission_id: str,
) -> list[str]:
    blockers: list[str] = []
    if control.mission_id != mission_id:
        blockers.append("release_control_mission_mismatch")
    if control.execution_integrity != ExecutionIntegrityState.VALIDATED:
        blockers.append(
            f"execution_integrity_{control.execution_integrity.value}"
        )
    if control.analysis_state != AnalysisState.SCHEMA_VALIDATED:
        blockers.append(f"analysis_{control.analysis_state.value}")
    if control.identity_state != IdentityResolutionState.RESOLVED:
        blockers.append(f"identity_{control.identity_state.value}")
    if control.target_sufficiency.rank < SufficiencyLevel.L4.rank:
        blockers.append("target_sufficiency_below_l4")
    if control.achieved_sufficiency.rank < SufficiencyLevel.L4.rank:
        blockers.append("sufficiency_below_l4")
    if control.achieved_sufficiency.rank < control.target_sufficiency.rank:
        blockers.append("target_sufficiency_not_reached")
    if control.unresolved_critical_conflicts:
        blockers.append("unresolved_critical_conflict")

    allowed_vertical_states = {
        VerticalState.VERIFIED,
        VerticalState.NOT_FOUND_AFTER_SUFFICIENT_SEARCH,
    }
    for vertical in control.required_verticals:
        if vertical.required and vertical.state not in allowed_vertical_states:
            blockers.append(
                f"required_vertical_{vertical.code}_{vertical.state.value}"
            )

    for provider in control.providers:
        if provider.required and provider.state != ProviderReadinessState.ACTIVE:
            blockers.append(
                f"required_provider_{provider.provider_ref}_{provider.state.value}"
            )

    if control.budget_state != BudgetState.WITHIN_BUDGET:
        blockers.append(f"budget_{control.budget_state.value}")
    return sorted(set(blockers))
