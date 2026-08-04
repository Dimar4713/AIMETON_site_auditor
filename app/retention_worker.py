from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic
from typing import Callable, Iterable

from app.trace_ledger import CleanupResult, SQLiteTraceLedger


@dataclass(frozen=True)
class RetentionRunSummary:
    started_at: datetime
    finished_at: datetime
    batches: int
    deleted: int
    protected: int
    stopped_reason: str


class RetentionCleanupWorker:
    """Runs expired-only cleanup in bounded batches without blocking product work."""

    def __init__(
        self,
        ledger: SQLiteTraceLedger,
        *,
        batch_size: int = 1000,
        max_batches: int = 10,
        max_runtime_seconds: float = 2.0,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if batch_size < 1 or batch_size > 10_000:
            raise ValueError("batch_size must be between 1 and 10000")
        if max_batches < 1 or max_batches > 1000:
            raise ValueError("max_batches must be between 1 and 1000")
        if max_runtime_seconds <= 0 or max_runtime_seconds > 60:
            raise ValueError("max_runtime_seconds must be in (0, 60]")
        self.ledger = ledger
        self.batch_size = batch_size
        self.max_batches = max_batches
        self.max_runtime_seconds = max_runtime_seconds
        self._now = now or (lambda: datetime.now(UTC))

    def run_once(self, *, protected_mission_ids: Iterable[str] = ()) -> RetentionRunSummary:
        started_at = self._now()
        started_clock = monotonic()
        deleted = 0
        protected = 0
        batches = 0
        stopped_reason = "no_expired_events"

        for _ in range(self.max_batches):
            if monotonic() - started_clock >= self.max_runtime_seconds:
                stopped_reason = "runtime_budget_exhausted"
                break
            result: CleanupResult = self.ledger.cleanup_expired(
                now=self._now(),
                batch_size=self.batch_size,
                protected_mission_ids=protected_mission_ids,
            )
            batches += 1
            deleted += result.deleted
            protected = max(protected, result.protected)
            if result.deleted < self.batch_size:
                stopped_reason = "no_more_expired_events"
                break
        else:
            stopped_reason = "batch_budget_exhausted"

        return RetentionRunSummary(
            started_at=started_at,
            finished_at=self._now(),
            batches=batches,
            deleted=deleted,
            protected=protected,
            stopped_reason=stopped_reason,
        )
