from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ContinuationPromotionPermit(BaseModel):
    """Versioned evidence permit for the first bounded steering family."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=1)
    total_scorable: int = Field(ge=1)
    continuation_decided: int = Field(ge=1)
    continuation_supported: int = Field(ge=0)
    continuation_contradicted: int = Field(ge=0)
    heterogeneous_batch_count: int = Field(ge=1)
    eligible_for_bounded_steering: bool


_VERIFIED_CONTINUATION_PERMIT = ContinuationPromotionPermit(
    evidence_id="search-observer-n30-2026-08-13",
    total_scorable=30,
    continuation_decided=8,
    continuation_supported=7,
    continuation_contradicted=1,
    heterogeneous_batch_count=4,
    eligible_for_bounded_steering=True,
)


def verified_continuation_promotion_permit() -> ContinuationPromotionPermit:
    """Return the reviewed code-versioned N=30 continuation permit.

    The retained causal corpus records N=30 globally and 8 decided continuation
    outcomes (7 supported, 1 contradicted) across heterogeneous batches. No
    unobserved confidence split or synthetic quality field is encoded here.
    Changing this permit requires a reviewed code change with fresh evidence.
    """
    return _VERIFIED_CONTINUATION_PERMIT.model_copy(deep=True)
