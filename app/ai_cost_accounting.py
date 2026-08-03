from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class AiCostAttempt(BaseModel):
    attempt: int = Field(ge=1)
    attempted_cost: float = Field(ge=0)
    billed_cost: float = Field(ge=0)
    accepted: bool
    accepted_cost: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_accepted_cost(self) -> "AiCostAttempt":
        expected = self.billed_cost if self.accepted else 0.0
        if abs(self.accepted_cost - expected) > 1e-9:
            raise ValueError("accepted_cost must equal billed_cost only for accepted attempts")
        return self


class AiCostLedger(BaseModel):
    status: Literal["within_budget", "budget_exceeded"]
    attempts: list[AiCostAttempt]
    max_attempts: int
    attempted_cost: float
    billed_cost: float
    accepted_cost: float
    remaining_budget: float
    client_release_eligible: bool


def account_ai_attempt_costs(
    attempts: list[AiCostAttempt | dict],
    *,
    max_attempts: int,
    budget: float,
) -> AiCostLedger:
    """Account attempted, billed and accepted cost without invoking a provider."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    if budget < 0:
        raise ValueError("budget must be non-negative")

    validated = [AiCostAttempt.model_validate(item) for item in attempts]
    if len(validated) > max_attempts:
        raise ValueError("attempt count exceeds max_attempts")
    if [item.attempt for item in validated] != list(range(1, len(validated) + 1)):
        raise ValueError("attempt numbers must be contiguous from 1")

    attempted_total = sum(item.attempted_cost for item in validated)
    billed_total = sum(item.billed_cost for item in validated)
    accepted_total = sum(item.accepted_cost for item in validated)
    remaining = budget - billed_total
    within_budget = billed_total <= budget

    return AiCostLedger(
        status="within_budget" if within_budget else "budget_exceeded",
        attempts=validated,
        max_attempts=max_attempts,
        attempted_cost=attempted_total,
        billed_cost=billed_total,
        accepted_cost=accepted_total,
        remaining_budget=max(remaining, 0.0),
        client_release_eligible=within_budget,
    )
