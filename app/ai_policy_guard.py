from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


ActionType = Literal[
    "crawl_url",
    "fetch_document",
    "query_provider",
    "resolve_identity",
    "review_conflict",
    "stop",
]


class AiNextAction(BaseModel):
    action_type: ActionType
    estimated_cost: float = Field(ge=0)
    estimated_latency_ms: int = Field(ge=0)


class PolicyContext(BaseModel):
    allowed_action_types: set[ActionType]
    remaining_budget: float = Field(ge=0)
    deadline_remaining_ms: int = Field(ge=0)
    rate_limit_available: bool = True
    robots_allowed: bool = True
    domain_allowed: bool = True
    ssrf_safe: bool = True
    authorized: bool = True


class GuardDecision(BaseModel):
    status: Literal["allowed", "blocked"]
    reason_code: Literal[
        "allowed",
        "action_type_forbidden",
        "budget_exceeded",
        "deadline_exceeded",
        "rate_limit_exhausted",
        "robots_forbidden",
        "domain_forbidden",
        "ssrf_blocked",
        "authorization_denied",
    ]
    executable: bool


def evaluate_ai_next_action(action: AiNextAction, policy: PolicyContext) -> GuardDecision:
    """Deterministically gate an AI-proposed action before any execution boundary."""
    checks = (
        (action.action_type not in policy.allowed_action_types, "action_type_forbidden"),
        (action.estimated_cost > policy.remaining_budget, "budget_exceeded"),
        (action.estimated_latency_ms > policy.deadline_remaining_ms, "deadline_exceeded"),
        (not policy.rate_limit_available, "rate_limit_exhausted"),
        (not policy.robots_allowed, "robots_forbidden"),
        (not policy.domain_allowed, "domain_forbidden"),
        (not policy.ssrf_safe, "ssrf_blocked"),
        (not policy.authorized, "authorization_denied"),
    )
    for blocked, reason_code in checks:
        if blocked:
            return GuardDecision(status="blocked", reason_code=reason_code, executable=False)
    return GuardDecision(status="allowed", reason_code="allowed", executable=True)
