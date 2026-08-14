from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.search_gap_shadow_refinement import ShadowRefinementPlan

ShadowSecondWaveAction = Literal["continue", "refine", "skip"]


@dataclass(frozen=True)
class ShadowSecondWaveDecision:
    action: ShadowSecondWaveAction
    reason_code: str
    gap_count: int
    suggestion_count: int
    routing_changed: bool = False
    steering_enabled: bool = False
    promotion_activated: bool = False


def decide_shadow_second_wave(plan: ShadowRefinementPlan) -> ShadowSecondWaveDecision:
    """Turn an observed refinement plan into advisory-only runtime intent.

    The decision is descriptive and cannot execute search. Duplicate/excluded
    pressure asks for query refinement; other unresolved gaps with bounded
    suggestions support another bounded wave in shadow; no suggestions means
    there is nothing executable to recommend.
    """
    if not plan.suggestions:
        return ShadowSecondWaveDecision(
            action="skip",
            reason_code="shadow_no_bounded_follow_up_available",
            gap_count=len(plan.gaps),
            suggestion_count=0,
        )

    if any(gap.code == "duplicate_or_excluded_pressure" for gap in plan.gaps):
        return ShadowSecondWaveDecision(
            action="refine",
            reason_code="shadow_refine_duplicate_or_excluded_pressure",
            gap_count=len(plan.gaps),
            suggestion_count=len(plan.suggestions),
        )

    return ShadowSecondWaveDecision(
        action="continue",
        reason_code="shadow_continue_unresolved_gap_with_bounded_follow_up",
        gap_count=len(plan.gaps),
        suggestion_count=len(plan.suggestions),
    )
