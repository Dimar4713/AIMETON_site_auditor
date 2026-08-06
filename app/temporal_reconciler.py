from __future__ import annotations

from dataclasses import dataclass

from app.temporal_orchestrator import (
    TemporalDecision,
    TemporalState,
    TrustedTime,
    evaluate_temporal_intent,
)
from app.temporal_repository import TemporalIntentRepository


@dataclass(frozen=True, slots=True)
class ReconcileItem:
    wait_id: str
    mission_id: str
    decision: TemporalDecision


@dataclass(frozen=True, slots=True)
class ReconcileResult:
    state: str
    reason: str
    items: tuple[ReconcileItem, ...]


class TemporalReconciler:
    """Read-only temporal classification cycle with no wake side effects."""

    def __init__(self, repository: TemporalIntentRepository) -> None:
        self._repository = repository

    def reconcile(self, now: TrustedTime) -> ReconcileResult:
        if not now.trusted:
            return ReconcileResult(
                state=TemporalState.BLOCKED.value,
                reason="blocked:untrusted_time",
                items=(),
            )

        items = tuple(
            ReconcileItem(
                wait_id=intent.wait_id,
                mission_id=intent.mission_id,
                decision=evaluate_temporal_intent(intent, now),
            )
            for intent in self._repository.list_intents()
        )
        return ReconcileResult(state="evaluated", reason="ok", items=items)
