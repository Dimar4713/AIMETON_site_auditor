from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel, ConfigDict, Field

from app.search_gap_hindsight import GapHindsightAssessment, GapHindsightVerdict
from app.search_gap_shadow_refinement import GapCode
from app.search_regime_utility import SearchRegime


class GapHindsightBucket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    effective_regime: SearchRegime
    gap_code: GapCode
    total: int = Field(ge=0)
    scorable: int = Field(ge=0)
    supported: int = Field(ge=0)
    contradicted: int = Field(ge=0)
    inconclusive: int = Field(ge=0)
    not_scorable: int = Field(ge=0)
    support_rate: float = Field(ge=0.0, le=1.0)
    contradiction_rate: float = Field(ge=0.0, le=1.0)


def aggregate_gap_hindsight(
    assessments: list[GapHindsightAssessment],
) -> list[GapHindsightBucket]:
    grouped: dict[tuple[SearchRegime, GapCode], list[GapHindsightAssessment]] = defaultdict(list)
    for item in assessments:
        grouped[(item.effective_regime, item.gap_code)].append(item)

    result: list[GapHindsightBucket] = []
    for (regime, gap_code), items in sorted(grouped.items(), key=lambda pair: (pair[0][0], pair[0][1])):
        supported = sum(item.verdict == GapHindsightVerdict.SUPPORTED for item in items)
        contradicted = sum(item.verdict == GapHindsightVerdict.CONTRADICTED for item in items)
        inconclusive = sum(item.verdict == GapHindsightVerdict.INCONCLUSIVE for item in items)
        not_scorable = sum(item.verdict == GapHindsightVerdict.NOT_SCORABLE for item in items)
        scorable = supported + contradicted + inconclusive
        result.append(GapHindsightBucket(
            effective_regime=regime,
            gap_code=gap_code,
            total=len(items),
            scorable=scorable,
            supported=supported,
            contradicted=contradicted,
            inconclusive=inconclusive,
            not_scorable=not_scorable,
            support_rate=round(supported / scorable, 6) if scorable else 0.0,
            contradiction_rate=round(contradicted / scorable, 6) if scorable else 0.0,
        ))
    return result
