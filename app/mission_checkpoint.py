from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, Field


class MissionCheckpoint(BaseModel):
    mission_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    sequence: int = Field(ge=0)
    phase: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_.-]+$")
    state_digest: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    document_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()


class ResumeDecision(BaseModel):
    status: Literal["resume", "already_applied", "blocked"]
    reason_code: Literal["checkpoint_accepted", "checkpoint_already_applied", "checkpoint_conflict"]
    next_sequence: int
    create_documents: tuple[str, ...] = ()
    create_evidence: tuple[str, ...] = ()


def checkpoint_digest(state: dict[str, Any]) -> str:
    canonical = json.dumps(state, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def decide_resume(
    checkpoint: MissionCheckpoint,
    *,
    persisted_sequence: int,
    persisted_state_digest: str | None,
    existing_document_ids: set[str],
    existing_evidence_ids: set[str],
) -> ResumeDecision:
    """Return an idempotent resume plan without mutating persistence."""
    if persisted_sequence > checkpoint.sequence:
        return ResumeDecision(
            status="already_applied",
            reason_code="checkpoint_already_applied",
            next_sequence=persisted_sequence,
        )
    if persisted_sequence == checkpoint.sequence:
        if persisted_state_digest == checkpoint.state_digest:
            return ResumeDecision(
                status="already_applied",
                reason_code="checkpoint_already_applied",
                next_sequence=persisted_sequence,
            )
        return ResumeDecision(
            status="blocked",
            reason_code="checkpoint_conflict",
            next_sequence=persisted_sequence,
        )
    return ResumeDecision(
        status="resume",
        reason_code="checkpoint_accepted",
        next_sequence=checkpoint.sequence,
        create_documents=tuple(sorted(set(checkpoint.document_ids) - existing_document_ids)),
        create_evidence=tuple(sorted(set(checkpoint.evidence_ids) - existing_evidence_ids)),
    )
