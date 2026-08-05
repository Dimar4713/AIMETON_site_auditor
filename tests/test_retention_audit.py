from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.retention_audit import SQLiteRetentionAuditLedger
from app.retention_worker import RetentionRunSummary


def summary(**overrides):
    started = datetime(2026, 8, 5, 0, 0, tzinfo=UTC)
    payload = dict(
        started_at=started,
        finished_at=started + timedelta(seconds=1),
        batches=2,
        deleted=15,
        protected=3,
        stopped_reason="no_more_expired_events",
    )
    payload.update(overrides)
    return RetentionRunSummary(**payload)


def test_retention_audit_is_durable_and_compact(tmp_path: Path):
    path = tmp_path / "runtime.sqlite3"
    ledger = SQLiteRetentionAuditLedger(path)
    run_id = ledger.append(summary())

    reopened = SQLiteRetentionAuditLedger(path)
    latest = reopened.latest()

    assert latest is not None
    assert latest["run_id"] == run_id
    assert latest["deleted"] == 15
    assert latest["protected"] == 3
    assert latest["stopped_reason"] == "no_more_expired_events"


def test_latest_returns_newest_finished_run(tmp_path: Path):
    path = tmp_path / "runtime.sqlite3"
    ledger = SQLiteRetentionAuditLedger(path)
    first = summary()
    second = summary(
        finished_at=first.finished_at + timedelta(minutes=5),
        deleted=1,
        stopped_reason="runtime_budget_exhausted",
    )

    ledger.append(first)
    latest_id = ledger.append(second)

    latest = ledger.latest()
    assert latest is not None
    assert latest["run_id"] == latest_id
    assert latest["deleted"] == 1


def test_negative_audit_counters_are_rejected(tmp_path: Path):
    ledger = SQLiteRetentionAuditLedger(tmp_path / "runtime.sqlite3")
    try:
        ledger.append(summary(deleted=-1))
    except ValueError as exc:
        assert "non-negative" in str(exc)
    else:
        raise AssertionError("negative retention audit counters must fail")
