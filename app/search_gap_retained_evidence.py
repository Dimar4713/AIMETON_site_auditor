from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.search_gap_hindsight import (
    GapHindsightAssessment,
    GapHindsightEvidence,
    assess_gap_hindsight,
)
from app.search_gap_hindsight_aggregation import aggregate_gap_hindsight
from app.search_gap_shadow_refinement import GapCode
from app.search_regime_utility import SearchRegime


class RetainedGapOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mission_id: str = Field(min_length=1, max_length=120)
    attempt_id: str = Field(min_length=1, max_length=120)
    follow_up_query: str = Field(min_length=1, max_length=500)
    gap_code: GapCode
    effective_regime: SearchRegime
    evidence: GapHindsightEvidence
    routing_changed: bool = False

    def assess(self) -> GapHindsightAssessment:
        if self.routing_changed:
            raise ValueError("gap_hindsight_requires_routing_unchanged")
        return assess_gap_hindsight(
            gap_code=self.gap_code,
            effective_regime=self.effective_regime,
            evidence=self.evidence,
        )


def build_gap_hindsight_report(records: list[RetainedGapOutcome]) -> dict[str, object]:
    assessments = [record.assess() for record in records]
    buckets = aggregate_gap_hindsight(assessments)
    return {
        "evidence_kind": "search_gap_hindsight",
        "record_count": len(records),
        "assessments": [item.model_dump(mode="json") for item in assessments],
        "buckets": [item.model_dump(mode="json") for item in buckets],
        "routing_changed": False,
        "steering_enabled": False,
        "promotion_activated": False,
    }
