from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.retention_audit import SQLiteRetentionAuditLedger
from app.retention_worker import RetentionCleanupWorker, RetentionRunSummary


@dataclass(frozen=True)
class RetentionServiceResult:
    run_id: str
    summary: RetentionRunSummary


class RetentionLifecycleOwner:
    """Single owner that runs bounded cleanup and durably records its summary."""

    def __init__(
        self,
        worker: RetentionCleanupWorker,
        audit: SQLiteRetentionAuditLedger,
    ) -> None:
        self.worker = worker
        self.audit = audit

    def run_once(self, *, protected_mission_ids: Iterable[str] = ()) -> RetentionServiceResult:
        summary = self.worker.run_once(protected_mission_ids=protected_mission_ids)
        run_id = self.audit.append(summary)
        return RetentionServiceResult(run_id=run_id, summary=summary)
