from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.mission_orchestrator import NextActionPlan, QuestionState, StopReason, SufficiencyLevel


class SufficiencyModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SufficiencyDimension(StrEnum):
    COVERAGE = "coverage"
    EVIDENCE_QUALITY = "evidence_quality"
    IDENTITY_RESOLUTION = "identity_resolution"
    SOURCE_RELIABILITY = "source_reliability"
    FRESHNESS = "freshness"
    CONSISTENCY = "consistency"
    EXECUTION_INTEGRITY = "execution_integrity"


class DimensionAssessment(SufficiencyModel):
    dimension: SufficiencyDimension
    level: SufficiencyLevel
    reason_codes: list[str] = Field(default_factory=list)


class SufficiencyDelta(SufficiencyModel):
    before: SufficiencyLevel
    after: SufficiencyLevel
    improved_dimensions: list[SufficiencyDimension] = Field(default_factory=list)
    critical_gaps: list[str] = Field(default_factory=list)


class SufficiencyTurnRecord(SufficiencyModel):
    schema_version: str = "0.1.0"
    mission_id: str
    analysis_id: str
    correlation_id: str
    turn_number: int = Field(ge=1)
    before_level: SufficiencyLevel
    after_level: SufficiencyLevel
    evidence_refs: list[str] = Field(default_factory=list)
    critical_gaps: list[str] = Field(default_factory=list)
    next_action_type: str
    next_action_target: str = ""
    next_action_deficit: str = ""
    next_action_reason: str
    recorded_at: datetime


class SufficiencyEvaluation(SufficiencyModel):
    schema_version: str = "0.2.0"
    mission_id: str
    target_level: SufficiencyLevel
    achieved_level: SufficiencyLevel
    dimensions: list[DimensionAssessment]
    question_states: dict[str, QuestionState]
    critical_gaps: list[str] = Field(default_factory=list)
    delta: SufficiencyDelta
    report_release_allowed: bool = False
    stop_reason: StopReason | None = None
    next_plan: NextActionPlan | None = None
    turn_record: SufficiencyTurnRecord | None = None
