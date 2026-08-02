from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.mission_orchestrator import SufficiencyLevel
from app.sufficiency_evaluator.models import SufficiencyEvaluation


class ResultUsage(StrEnum):
    INTERNAL_ONLY = "internal_only"
    CLIENT_REPORT = "client_report"


class SufficiencyProjection(BaseModel):
    """Stable UI/Report projection of a sufficiency evaluation."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "0.1.0"
    mission_id: str
    target_level: SufficiencyLevel
    achieved_level: SufficiencyLevel
    reason_codes: list[str] = Field(default_factory=list)
    allowed_usage: ResultUsage
    report_release_allowed: bool


def project_sufficiency(evaluation: SufficiencyEvaluation) -> SufficiencyProjection:
    reason_codes = list(evaluation.critical_gaps)
    for dimension in evaluation.dimensions:
        reason_codes.extend(dimension.reason_codes)
    reason_codes = list(dict.fromkeys(reason_codes))

    allowed_usage = (
        ResultUsage.CLIENT_REPORT
        if evaluation.report_release_allowed
        else ResultUsage.INTERNAL_ONLY
    )
    return SufficiencyProjection(
        mission_id=evaluation.mission_id,
        target_level=evaluation.target_level,
        achieved_level=evaluation.achieved_level,
        reason_codes=reason_codes,
        allowed_usage=allowed_usage,
        report_release_allowed=evaluation.report_release_allowed,
    )
