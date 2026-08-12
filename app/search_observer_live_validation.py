from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LiveValidationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LiveSecondWaveValidationContract(LiveValidationModel):
    """Fail-closed policy contract for a future bounded live second-wave validation.

    This model is descriptive only. It cannot execute searches, call providers,
    change routing, or authorize spend by itself.
    """

    wave_count: int = Field(default=2, ge=2, le=2)
    max_incremental_queries: int = Field(default=4, ge=1, le=4)
    allow_paid_calls: bool = False
    max_incremental_cost_rub: float = Field(default=0.0, ge=0.0)
    owner_spend_authorized: bool = False
    allow_premium_escalation: bool = False
    routing_changed: bool = False
    preserve_provider_policy: bool = True
    preserve_concurrency_limits: bool = True
    preserve_cooldown_and_circuits: bool = True

    @model_validator(mode="after")
    def validate_safety_contract(self) -> "LiveSecondWaveValidationContract":
        if self.routing_changed:
            raise ValueError("live_validation_requires_routing_unchanged")
        if not self.preserve_provider_policy:
            raise ValueError("live_validation_requires_provider_policy_authority")
        if not self.preserve_concurrency_limits:
            raise ValueError("live_validation_requires_concurrency_limits")
        if not self.preserve_cooldown_and_circuits:
            raise ValueError("live_validation_requires_cooldown_and_circuits")
        if self.allow_premium_escalation:
            raise ValueError("premium_escalation_not_authorized")
        if self.max_incremental_cost_rub > 0.0 and not self.allow_paid_calls:
            raise ValueError("positive_cost_requires_paid_calls_enabled")
        if self.allow_paid_calls and not self.owner_spend_authorized:
            raise ValueError("paid_calls_require_owner_spend_authorization")
        if self.max_incremental_cost_rub > 0.0 and not self.owner_spend_authorized:
            raise ValueError("positive_cost_requires_owner_spend_authorization")
        return self

    @property
    def spend_gate_open(self) -> bool:
        return bool(
            self.allow_paid_calls
            and self.owner_spend_authorized
            and self.max_incremental_cost_rub > 0.0
        )

    @property
    def zero_cost_only(self) -> bool:
        return self.max_incremental_cost_rub == 0.0 and not self.allow_paid_calls
