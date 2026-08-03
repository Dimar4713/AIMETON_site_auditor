from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TrustedAiContext(BaseModel):
    allowed_source_ids: set[str]
    allowed_entity_ids: set[str]
    allowed_action_types: set[str]
    remaining_budget: float = Field(ge=0)


class UntrustedAiProposal(BaseModel):
    claim: str
    source_ids: list[str] = Field(min_length=1)
    entity_ids: list[str] = Field(default_factory=list)
    action_type: str | None = None
    estimated_cost: float = Field(default=0, ge=0)
    requested_policy_overrides: dict[str, object] = Field(default_factory=dict)


class PromptBoundaryDecision(BaseModel):
    status: Literal["accepted", "blocked"]
    reason_code: Literal[
        "accepted",
        "prompt_injection_attempt",
        "unsupported_source",
        "unsupported_entity",
        "action_type_forbidden",
        "budget_exceeded",
    ]
    client_release_eligible: bool
    executable: bool


def validate_untrusted_ai_proposal(
    proposal: UntrustedAiProposal,
    *,
    trusted: TrustedAiContext,
) -> PromptBoundaryDecision:
    """Treat document/model content as data; only trusted context can define policy."""
    if proposal.requested_policy_overrides:
        return PromptBoundaryDecision(
            status="blocked",
            reason_code="prompt_injection_attempt",
            client_release_eligible=False,
            executable=False,
        )
    if set(proposal.source_ids) - trusted.allowed_source_ids:
        return PromptBoundaryDecision(
            status="blocked",
            reason_code="unsupported_source",
            client_release_eligible=False,
            executable=False,
        )
    if set(proposal.entity_ids) - trusted.allowed_entity_ids:
        return PromptBoundaryDecision(
            status="blocked",
            reason_code="unsupported_entity",
            client_release_eligible=False,
            executable=False,
        )
    if proposal.action_type is not None and proposal.action_type not in trusted.allowed_action_types:
        return PromptBoundaryDecision(
            status="blocked",
            reason_code="action_type_forbidden",
            client_release_eligible=False,
            executable=False,
        )
    if proposal.estimated_cost > trusted.remaining_budget:
        return PromptBoundaryDecision(
            status="blocked",
            reason_code="budget_exceeded",
            client_release_eligible=False,
            executable=False,
        )
    return PromptBoundaryDecision(
        status="accepted",
        reason_code="accepted",
        client_release_eligible=True,
        executable=proposal.action_type is not None,
    )
