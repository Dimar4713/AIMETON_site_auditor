from datetime import UTC, datetime
from pathlib import Path

from app.retention_audit import SQLiteRetentionAuditLedger
from app.retention_service import RetentionLifecycleOwner
from app.retention_worker import RetentionCleanupWorker
from app.trace_ledger import SQLiteTraceLedger


def test_lifecycle_owner_runs_cleanup_and_persists_summary(tmp_path: Path):
    path = tmp_path / "runtime.sqlite3"
    worker = RetentionCleanupWorker(
        SQLiteTraceLedger(path),
        batch_size=10,
        max_batches=1,
        now=lambda: datetime(2026, 8, 5, 0, 0, tzinfo=UTC),
    )
    audit = SQLiteRetentionAuditLedger(path)
    owner = RetentionLifecycleOwner(worker, audit)

    result = owner.run_once(protected_mission_ids={"mission-active"})

    assert result.run_id.startswith("retention_")
    latest = audit.latest()
    assert latest is not None
    assert latest["run_id"] == result.run_id
    assert latest["deleted"] == result.summary.deleted
    assert latest["stopped_reason"] == result.summary.stopped_reason


def test_lifecycle_owner_forwards_protected_missions(tmp_path: Path):
    class Worker:
        def __init__(self):
            self.protected = None

        def run_once(self, *, protected_mission_ids=()):
            self.protected = tuple(protected_mission_ids)
            from app.retention_worker import RetentionRunSummary
            now = datetime(2026, 8, 5, 0, 0, tzinfo=UTC)
            return RetentionRunSummary(now, now, 1, 0, 0, "no_more_expired_events")

    worker = Worker()
    audit = SQLiteRetentionAuditLedger(tmp_path / "runtime.sqlite3")
    owner = RetentionLifecycleOwner(worker, audit)

    owner.run_once(protected_mission_ids={"m1", "m2"})

    assert set(worker.protected) == {"m1", "m2"}
