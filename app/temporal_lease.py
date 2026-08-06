from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from app.temporal_orchestrator import TrustedTime


class LeaseBlocked(RuntimeError):
    pass


class LeaseConflict(RuntimeError):
    pass


class LeaseVersionConflict(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TemporalLease:
    wait_id: str
    holder_id: str
    idempotency_key: str
    acquired_at: datetime
    expires_at: datetime
    version: int
    released: bool = False


class TemporalLeaseRepository:
    """SQLite lease store driven exclusively by injected AIMETON trusted time."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS temporal_leases (
                    wait_id TEXT PRIMARY KEY,
                    holder_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    acquired_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    released INTEGER NOT NULL DEFAULT 0
                )
                """
            )

    def get(self, wait_id: str) -> TemporalLease | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM temporal_leases WHERE wait_id = ?", (wait_id,)
            ).fetchone()
        return None if row is None else _row_to_lease(row)

    def acquire(
        self,
        *,
        wait_id: str,
        holder_id: str,
        idempotency_key: str,
        now: TrustedTime,
        ttl_seconds: int,
    ) -> TemporalLease:
        _validate_request(wait_id, holder_id, idempotency_key, ttl_seconds)
        _require_trusted(now)
        expires_at = now.utc + timedelta(seconds=ttl_seconds)

        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute(
                    "SELECT * FROM temporal_leases WHERE wait_id = ?", (wait_id,)
                ).fetchone()
                if row is not None:
                    current = _row_to_lease(row)
                    active = not current.released and current.expires_at > now.utc
                    if active:
                        if (
                            current.holder_id == holder_id
                            and current.idempotency_key == idempotency_key
                        ):
                            db.execute("COMMIT")
                            return current
                        raise LeaseConflict("lease_active:held_by_other")
                    version = current.version + 1
                    db.execute(
                        """
                        UPDATE temporal_leases
                        SET holder_id = ?, idempotency_key = ?, acquired_at = ?,
                            expires_at = ?, version = ?, released = 0
                        WHERE wait_id = ? AND version = ?
                        """,
                        (
                            holder_id,
                            idempotency_key,
                            _iso(now.utc),
                            _iso(expires_at),
                            version,
                            wait_id,
                            current.version,
                        ),
                    )
                    if db.total_changes != 1:
                        raise LeaseVersionConflict("stale_lease_version")
                else:
                    version = 1
                    db.execute(
                        """
                        INSERT INTO temporal_leases(
                            wait_id, holder_id, idempotency_key, acquired_at,
                            expires_at, version, released
                        ) VALUES (?, ?, ?, ?, ?, ?, 0)
                        """,
                        (
                            wait_id,
                            holder_id,
                            idempotency_key,
                            _iso(now.utc),
                            _iso(expires_at),
                            version,
                        ),
                    )
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
        return TemporalLease(
            wait_id=wait_id,
            holder_id=holder_id,
            idempotency_key=idempotency_key,
            acquired_at=now.utc,
            expires_at=expires_at,
            version=version,
        )

    def renew(
        self,
        *,
        wait_id: str,
        holder_id: str,
        expected_version: int,
        now: TrustedTime,
        ttl_seconds: int,
    ) -> TemporalLease:
        _validate_request(wait_id, holder_id, "renew", ttl_seconds)
        _require_trusted(now)
        expires_at = now.utc + timedelta(seconds=ttl_seconds)

        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute(
                    "SELECT * FROM temporal_leases WHERE wait_id = ?", (wait_id,)
                ).fetchone()
                if row is None:
                    raise LeaseConflict("lease_not_found")
                current = _row_to_lease(row)
                if current.released or current.expires_at <= now.utc:
                    raise LeaseConflict("lease_not_active")
                if current.holder_id != holder_id:
                    raise LeaseConflict("lease_holder_mismatch")
                if current.version != expected_version:
                    raise LeaseVersionConflict("stale_lease_version")
                new_version = current.version + 1
                cursor = db.execute(
                    """
                    UPDATE temporal_leases
                    SET expires_at = ?, version = ?
                    WHERE wait_id = ? AND holder_id = ? AND version = ? AND released = 0
                    """,
                    (_iso(expires_at), new_version, wait_id, holder_id, expected_version),
                )
                if cursor.rowcount != 1:
                    raise LeaseVersionConflict("stale_lease_version")
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
        return TemporalLease(
            wait_id=current.wait_id,
            holder_id=current.holder_id,
            idempotency_key=current.idempotency_key,
            acquired_at=current.acquired_at,
            expires_at=expires_at,
            version=new_version,
        )

    def release(
        self,
        *,
        wait_id: str,
        holder_id: str,
        now: TrustedTime,
    ) -> TemporalLease:
        _validate_request(wait_id, holder_id, "release", 1)
        _require_trusted(now)

        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute(
                    "SELECT * FROM temporal_leases WHERE wait_id = ?", (wait_id,)
                ).fetchone()
                if row is None:
                    raise LeaseConflict("lease_not_found")
                current = _row_to_lease(row)
                if current.holder_id != holder_id:
                    raise LeaseConflict("lease_holder_mismatch")
                if current.released:
                    db.execute("COMMIT")
                    return current
                new_version = current.version + 1
                cursor = db.execute(
                    """
                    UPDATE temporal_leases
                    SET released = 1, version = ?
                    WHERE wait_id = ? AND holder_id = ? AND version = ?
                    """,
                    (new_version, wait_id, holder_id, current.version),
                )
                if cursor.rowcount != 1:
                    raise LeaseVersionConflict("stale_lease_version")
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
        return TemporalLease(
            wait_id=current.wait_id,
            holder_id=current.holder_id,
            idempotency_key=current.idempotency_key,
            acquired_at=current.acquired_at,
            expires_at=current.expires_at,
            version=new_version,
            released=True,
        )


def _validate_request(
    wait_id: str, holder_id: str, idempotency_key: str, ttl_seconds: int
) -> None:
    if not wait_id.strip() or not holder_id.strip() or not idempotency_key.strip():
        raise ValueError("wait_id, holder_id and idempotency_key must not be empty")
    if ttl_seconds <= 0:
        raise ValueError("ttl_seconds must be positive")


def _require_trusted(now: TrustedTime) -> None:
    if not now.trusted:
        raise LeaseBlocked("blocked:untrusted_time")


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _row_to_lease(row: sqlite3.Row) -> TemporalLease:
    return TemporalLease(
        wait_id=row["wait_id"],
        holder_id=row["holder_id"],
        idempotency_key=row["idempotency_key"],
        acquired_at=_parse(row["acquired_at"]),
        expires_at=_parse(row["expires_at"]),
        version=int(row["version"]),
        released=bool(row["released"]),
    )
