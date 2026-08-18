from __future__ import annotations

from enum import StrEnum
from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field

from app.search_observer_llm import DirectionRecommendation, ObserverAction
from app.search_observer_promotion import (
    ActionFamily,
    PromotionDecision,
    PromotionState,
)


class SteeringModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SteeringState(StrEnum):
    DISABLED = "disabled"
    REJECTED = "rejected"
    ACCEPTED = "accepted"


class BoundedSteeringDecision(SteeringModel):
    state: SteeringState
    routing_changed: bool = False
    accepted_direction_indexes: list[int] = Field(default_factory=list)
    accepted_actions: list[ObserverAction] = Field(default_factory=list)
    rejected_action_count: int = Field(default=0, ge=0)
    max_second_wave_queries: int = Field(default=0, ge=0)
    reason_codes: list[str] = Field(default_factory=list)


def _continuation_family_eligible(promotion: PromotionDecision | None) -> bool:
    if promotion is None or promotion.state != PromotionState.ELIGIBLE_FOR_BOUNDED_STEERING:
        return False
    return any(
        item.family == ActionFamily.CONTINUATION
        and item.state == PromotionState.ELIGIBLE_FOR_BOUNDED_STEERING
        for item in promotion.families
    )


def validate_bounded_continuation_steering(
    recommendations: Iterable[DirectionRecommendation],
    *,
    enabled: bool,
    promotion: PromotionDecision | None,
    remaining_query_budget: int,
    effective_regime: str,
    direction_count: int,
) -> BoundedSteeringDecision:
    """Validate the first reversible Phase-D steering envelope.

    This function has no provider execution capability. It can only admit
    already-bounded continuation-family directions for a later deterministic
    scheduler. Adjustment, stop and economic actions stay shadow-only.
    """
    if not enabled:
        return BoundedSteeringDecision(
            state=SteeringState.DISABLED,
            reason_codes=["runtime_gate_disabled"],
        )

    if remaining_query_budget <= 0:
        return BoundedSteeringDecision(
            state=SteeringState.REJECTED,
            reason_codes=["no_remaining_query_budget"],
        )

    if direction_count <= 0:
        return BoundedSteeringDecision(
            state=SteeringState.REJECTED,
            reason_codes=["no_search_directions"],
        )

    if effective_regime not in {"precision", "balanced", "discovery"}:
        return BoundedSteeringDecision(
            state=SteeringState.REJECTED,
            reason_codes=["invalid_effective_search_regime"],
        )

    if not _continuation_family_eligible(promotion):
        return BoundedSteeringDecision(
            state=SteeringState.REJECTED,
            reason_codes=["continuation_promotion_gate_not_satisfied"],
        )

    accepted_indexes: list[int] = []
    accepted_actions: list[ObserverAction] = []
    rejected = 0
    seen: set[int] = set()

    for item in recommendations:
        if item.action not in {ObserverAction.CONTINUE, ObserverAction.BOOST}:
            rejected += 1
            continue
        if item.direction_index < 0 or item.direction_index >= direction_count:
            rejected += 1
            continue
        if item.direction_index in seen:
            continue
        seen.add(item.direction_index)
        accepted_indexes.append(item.direction_index)
        accepted_actions.append(item.action)
        if len(accepted_indexes) >= remaining_query_budget:
            break

    if not accepted_indexes:
        return BoundedSteeringDecision(
            state=SteeringState.REJECTED,
            rejected_action_count=rejected,
            reason_codes=["no_eligible_continuation_recommendations"],
        )

    return BoundedSteeringDecision(
        state=SteeringState.ACCEPTED,
        routing_changed=False,
        accepted_direction_indexes=accepted_indexes,
        accepted_actions=accepted_actions,
        rejected_action_count=rejected,
        max_second_wave_queries=min(remaining_query_budget, len(accepted_indexes)),
        reason_codes=["bounded_continuation_admitted_for_scheduler"],
    )
