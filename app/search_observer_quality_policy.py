from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.search_observer_promotion import QualityGuard
from app.search_observer_quality import QualityMetrics


class QualityPolicyModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QualityFirstPromotionPolicy(QualityPolicyModel):
    """Owner-approved validation policy for the current Search Observer phase.

    Search quality dominates optimization cost. Qualified and direct/official
    yield may not regress, and duplicate/excluded waste may not increase.
    Latency and cost are not compared by an arbitrary relative multiplier here;
    they are accepted only when the existing operational hard-cap envelope is
    explicitly confirmed by the caller.
    """

    max_qualified_yield_drop_ratio: float = 0.0
    max_direct_or_official_yield_drop_ratio: float = 0.0
    max_waste_ratio_increase: float = 0.0
    resource_policy_mode: str = "existing_hard_caps"


def derive_quality_first_guard(
    *,
    baseline: QualityMetrics,
    candidate: QualityMetrics,
    resource_policy_compliant: bool | None,
    policy: QualityFirstPromotionPolicy | None = None,
) -> QualityGuard:
    """Build the quality-first promotion guard without inventing cost multipliers.

    `resource_policy_compliant` must come from the existing bounded runtime/spend
    contract. If it is unknown, the guard remains incomplete and promotion stays
    fail-closed.
    """

    limits = policy or QualityFirstPromotionPolicy()
    qualified_regressed = (
        candidate.qualified_per_query
        < baseline.qualified_per_query * (1.0 - limits.max_qualified_yield_drop_ratio)
        if baseline.qualified_per_query > 0.0
        else False
    )
    direct_regressed = (
        candidate.direct_or_official_per_query
        < baseline.direct_or_official_per_query
        * (1.0 - limits.max_direct_or_official_yield_drop_ratio)
        if baseline.direct_or_official_per_query > 0.0
        else False
    )
    waste_regressed = (
        candidate.waste_ratio > baseline.waste_ratio + limits.max_waste_ratio_increase
    )

    return QualityGuard(
        qualified_yield_regressed=qualified_regressed,
        direct_or_official_yield_regressed=direct_regressed,
        duplicate_or_excluded_waste_regressed=waste_regressed,
        latency_or_cost_outside_policy=(
            None if resource_policy_compliant is None else not resource_policy_compliant
        ),
    )
