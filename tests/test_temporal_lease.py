from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.temporal_lease import (
    LeaseBlocked,
    LeaseConflict,
    LeaseVersionConflict,
    TemporalLeaseRepository,
)
from app.temporal_orchestrator import TrustedTime


def trusted(at: datetime) -> TrustedTime:
    return TrustedTime(
        utc=at,
        source="chrony",
        synced=True,
        quality="trusted",
        offset_ms=0.5,
        stratum=2,
    )


def untrusted(at: datetime) -> TrustedTime:
    return TrustedTime(
        utc=at,
        source="system",
        synced=False,
        quality="untrusted",
        offset_ms=999,
        stratum=16,
    )


def test_same_holder_idempotent_acquire_returns_same_lease(tmp_path) -> None:
    repo = TemporalLeaseRepository(tmp_path / "lease.sqlite3")
    now = trusted(datetime(2026, 8, 6, 14, 0, tzinfo=timezone.utc))

    first = repo.acquire(
        wait_id="wait-1",
        holder_id="agent-a",
        idempotency_key="claim-1",
        now=now,
        ttl_seconds=60,
    )
    second = repo.acquire(
        wait_id="wait-1",
        holder_id="agent-a",
        idempotency_key="claim-1",
        now=now,
        ttl_seconds=60,
    )

    assert second == first
    assert repo.get("wait-1") == first


def test_other_holder_conflicts_while_lease_active(tmp_path) -> None:
    repo = TemporalLeaseRepository(tmp_path / "lease.sqlite3")
    now = trusted(datetime(2026, 8, 6, 14, 0, tzinfo=timezone.utc))
    repo.acquire(
        wait_id="wait-1",
        holder_id="agent-a",
        idempotency_key="claim-a",
        now=now,
        ttl_seconds=60,
    )

    with pytest.raises(LeaseConflict, match="lease_active"):
        repo.acquire(
            wait_id="wait-1",
            holder_id="agent-b",
            idempotency_key="claim-b",
            now=now,
            ttl_seconds=60,
        )

    assert repo.get("wait-1").holder_id == "agent-a"


def test_expired_lease_can_be_taken_over_by_new_holder(tmp_path) -> None:
    repo = TemporalLeaseRepository(tmp_path / "lease.sqlite3")
    start = datetime(2026, 8, 6, 14, 0, tzinfo=timezone.utc)
    first = repo.acquire(
        wait_id="wait-1",
        holder_id="agent-a",
        idempotency_key="claim-a",
        now=trusted(start),
        ttl_seconds=30,
    )
    second = repo.acquire(
        wait_id="wait-1",
        holder_id="agent-b",
        idempotency_key="claim-b",
        now=trusted(start + timedelta(seconds=30)),
        ttl_seconds=90,
    )

    assert second.holder_id == "agent-b"
    assert second.version == first.version + 1
    assert repo.get("wait-1") == second


def test_untrusted_time_blocks_without_mutation(tmp_path) -> None:
    repo = TemporalLeaseRepository(tmp_path / "lease.sqlite3")
    at = datetime(2026, 8, 6, 14, 0, tzinfo=timezone.utc)

    with pytest.raises(LeaseBlocked, match="blocked:untrusted_time"):
        repo.acquire(
            wait_id="wait-1",
            holder_id="agent-a",
            idempotency_key="claim-a",
            now=untrusted(at),
            ttl_seconds=60,
        )

    assert repo.get("wait-1") is None


def test_renew_requires_current_holder_and_version(tmp_path) -> None:
    repo = TemporalLeaseRepository(tmp_path / "lease.sqlite3")
    at = datetime(2026, 8, 6, 14, 0, tzinfo=timezone.utc)
    lease = repo.acquire(
        wait_id="wait-1",
        holder_id="agent-a",
        idempotency_key="claim-a",
        now=trusted(at),
        ttl_seconds=60,
    )

    with pytest.raises(LeaseConflict, match="holder_mismatch"):
        repo.renew(
            wait_id="wait-1",
            holder_id="agent-b",
            expected_version=lease.version,
            now=trusted(at + timedelta(seconds=10)),
            ttl_seconds=60,
        )

    with pytest.raises(LeaseVersionConflict, match="stale_lease_version"):
        repo.renew(
            wait_id="wait-1",
            holder_id="agent-a",
            expected_version=99,
            now=trusted(at + timedelta(seconds=10)),
            ttl_seconds=60,
        )

    renewed = repo.renew(
        wait_id="wait-1",
        holder_id="agent-a",
        expected_version=lease.version,
        now=trusted(at + timedelta(seconds=10)),
        ttl_seconds=120,
    )
    assert renewed.version == lease.version + 1
    assert renewed.expires_at == at + timedelta(seconds=130)


def test_release_is_idempotent_for_holder_and_foreign_release_fails(tmp_path) -> None:
    repo = TemporalLeaseRepository(tmp_path / "lease.sqlite3")
    at = datetime(2026, 8, 6, 14, 0, tzinfo=timezone.utc)
    repo.acquire(
        wait_id="wait-1",
        holder_id="agent-a",
        idempotency_key="claim-a",
        now=trusted(at),
        ttl_seconds=60,
    )

    with pytest.raises(LeaseConflict, match="holder_mismatch"):
        repo.release(wait_id="wait-1", holder_id="agent-b", now=trusted(at))

    first = repo.release(wait_id="wait-1", holder_id="agent-a", now=trusted(at))
    second = repo.release(wait_id="wait-1", holder_id="agent-a", now=trusted(at))

    assert first.released is True
    assert second == first


def test_untrusted_renew_and_release_leave_lease_unchanged(tmp_path) -> None:
    repo = TemporalLeaseRepository(tmp_path / "lease.sqlite3")
    at = datetime(2026, 8, 6, 14, 0, tzinfo=timezone.utc)
    original = repo.acquire(
        wait_id="wait-1",
        holder_id="agent-a",
        idempotency_key="claim-a",
        now=trusted(at),
        ttl_seconds=60,
    )

    with pytest.raises(LeaseBlocked):
        repo.renew(
            wait_id="wait-1",
            holder_id="agent-a",
            expected_version=original.version,
            now=untrusted(at),
            ttl_seconds=60,
        )
    with pytest.raises(LeaseBlocked):
        repo.release(wait_id="wait-1", holder_id="agent-a", now=untrusted(at))

    assert repo.get("wait-1") == original
