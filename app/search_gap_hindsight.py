from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.search_gap_shadow_refinement import GapCode
from app.search_regime_utility import SearchRegime


class GapHindsightVerdict(StrEnum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    INCONCLUSIVE = "inconclusive"
    NOT_SCORABLE = "not_scorable"


class GapHindsightEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    added_raw_results: int = Field(ge=0)
    added_unique_domains: int = Field(ge=0)
    added_qualified_candidates: int = Field(ge=0)
    added_direct_or_official_candidates: int = Field(ge=0)
    duplicate_results: int = Field(ge=0)
    excluded_results: int = Field(ge=0)
    region_confirmed_candidates: int = Field(ge=0, default=0)
    industry_confirmed_candidates: int = Field(ge=0, default=0)
    novel_entities: int | None = Field(default=None, ge=0)
    rare_hits: int | None = Field(default=None, ge=0)

    @property
    def waste_ratio(self) -> float:
        if self.added_raw_results <= 0:
            return 0.0
        wasted = min(self.added_raw_results, self.duplicate_results + self.excluded_results)
        return round(wasted / self.added_raw_results, 6)


class GapHindsightAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gap_code: GapCode
    effective_regime: SearchRegime
    verdict: GapHindsightVerdict
    reason_code: str
    routing_changed: bool = False
    steering_enabled: bool = False


def assess_gap_hindsight(
    *,
    gap_code: GapCode,
    effective_regime: SearchRegime,
    evidence: GapHindsightEvidence,
) -> GapHindsightAssessment:
    verdict = GapHindsightVerdict.INCONCLUSIVE
    reason = "gap_hindsight_inconclusive"

    if gap_code == "sparse_yield":
        if evidence.added_unique_domains > 0 or evidence.added_qualified_candidates > 0:
            verdict, reason = GapHindsightVerdict.SUPPORTED, "sparse_gap_closed_by_new_yield"
        elif evidence.added_raw_results > 0:
            verdict, reason = GapHindsightVerdict.CONTRADICTED, "sparse_gap_follow_up_added_no_unique_or_qualified_yield"

    elif gap_code == "duplicate_or_excluded_pressure":
        if evidence.added_raw_results > 0 and evidence.added_unique_domains > 0 and evidence.waste_ratio < 0.45:
            verdict, reason = GapHindsightVerdict.SUPPORTED, "waste_pressure_reduced"
        elif evidence.added_raw_results > 0 and evidence.added_unique_domains == 0:
            verdict, reason = GapHindsightVerdict.CONTRADICTED, "follow_up_added_no_new_unique_domains"
        elif evidence.added_raw_results > 0 and evidence.waste_ratio >= 0.45:
            verdict, reason = GapHindsightVerdict.CONTRADICTED, "waste_pressure_persisted"

    elif gap_code == "no_returned_candidates":
        if evidence.added_direct_or_official_candidates > 0 or evidence.added_qualified_candidates > 0:
            verdict, reason = GapHindsightVerdict.SUPPORTED, "returnable_candidate_evidence_added"
        elif evidence.added_raw_results > 0:
            verdict, reason = GapHindsightVerdict.CONTRADICTED, "follow_up_added_no_returnable_candidate"

    elif gap_code == "region_confirmation_missing":
        if evidence.region_confirmed_candidates > 0:
            verdict, reason = GapHindsightVerdict.SUPPORTED, "region_evidence_added"
        elif evidence.added_qualified_candidates > 0:
            verdict, reason = GapHindsightVerdict.CONTRADICTED, "qualified_follow_up_still_missing_region_evidence"

    elif gap_code == "industry_confirmation_missing":
        if evidence.industry_confirmed_candidates > 0:
            verdict, reason = GapHindsightVerdict.SUPPORTED, "industry_evidence_added"
        elif evidence.added_qualified_candidates > 0:
            verdict, reason = GapHindsightVerdict.CONTRADICTED, "qualified_follow_up_still_missing_industry_evidence"

    elif gap_code == "discovery_novelty_unmeasured":
        if evidence.novel_entities is None and evidence.rare_hits is None:
            verdict, reason = GapHindsightVerdict.NOT_SCORABLE, "discovery_requires_explicit_novelty_evidence"
        elif (evidence.novel_entities or 0) + (evidence.rare_hits or 0) > 0:
            verdict, reason = GapHindsightVerdict.SUPPORTED, "discovery_novelty_observed"
        else:
            verdict, reason = GapHindsightVerdict.CONTRADICTED, "discovery_follow_up_added_no_novel_or_rare_hits"

    return GapHindsightAssessment(
        gap_code=gap_code,
        effective_regime=effective_regime,
        verdict=verdict,
        reason_code=reason,
    )
