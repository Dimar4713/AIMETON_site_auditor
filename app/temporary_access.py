from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
from pathlib import Path
import secrets
import sqlite3

from app.auth import LocalAuthProvider, Session, User, UserRole


TOKEN_PREFIX = "aimeton_tmp_"
ALLOWED_PURPOSES = {"agent", "marketing_demo", "support", "other"}


@dataclass(frozen=True)
class TemporaryAccess:
    id: int
    subject_user_id: int
    label: str
    purpose: str
    created_by_user_id: int
    created_at: datetime
    expires_at: datetime
    max_uses: int
    uses_count: int
    last_used_at: datetime | None
    revoked_at: datetime | None


@dataclass(frozen=True)
class IssuedTemporaryAccess:
    access: TemporaryAccess
    token: str


class TemporaryAccessRepository:
    def __init__(self, database_path: str | Path):
        self.path = str(database_path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS temporary_access_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    token_digest TEXT NOT NULL UNIQUE,
                    subject_user_id INTEGER NOT NULL REFERENCES users(id),
                    label TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    created_by_user_id INTEGER NOT NULL REFERENCES users(id),
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    max_uses INTEGER NOT NULL CHECK(max_uses > 0),
                    uses_count INTEGER NOT NULL DEFAULT 0,
                    last_used_at TEXT,
                    revoked_at TEXT,
                    revoked_by_user_id INTEGER,
                    revocation_reason TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS temporary_access_sessions (
                    session_token_hash TEXT PRIMARY KEY,
                    temporary_access_id INTEGER NOT NULL REFERENCES temporary_access_tokens(id),
                    created_at TEXT NOT NULL
                )
                """
            )

    @staticmethod
    def digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _row_to_access(row: sqlite3.Row) -> TemporaryAccess:
        return TemporaryAccess(
            id=int(row["id"]),
            subject_user_id=int(row["subject_user_id"]),
            label=row["label"],
            purpose=row["purpose"],
            created_by_user_id=int(row["created_by_user_id"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"]),
            max_uses=int(row["max_uses"]),
            uses_count=int(row["uses_count"]),
            last_used_at=datetime.fromisoformat(row["last_used_at"]) if row["last_used_at"] else None,
            revoked_at=datetime.fromisoformat(row["revoked_at"]) if row["revoked_at"] else None,
        )

    def issue(
        self,
        *,
        subject: User,
        actor: User,
        label: str,
        purpose: str,
        expires_at: datetime,
        max_uses: int,
        reason: str,
    ) -> IssuedTemporaryAccess:
        now = datetime.now(UTC)
        normalized_label = label.strip()
        normalized_reason = reason.strip()
        if not normalized_label or not normalized_reason:
            raise ValueError("label and reason are required")
        if purpose not in ALLOWED_PURPOSES:
            raise ValueError("invalid purpose")
        if max_uses < 1 or max_uses > 1000:
            raise ValueError("invalid max_uses")
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= now or expires_at > now + timedelta(days=30):
            raise ValueError("expiry must be within 30 days")
        if not subject.is_active:
            raise PermissionError("inactive subject")
        if subject.role is UserRole.ADMIN:
            raise PermissionError("temporary admin access is disabled")

        token = TOKEN_PREFIX + secrets.token_urlsafe(32)
        token_digest = self.digest(token)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                INSERT INTO temporary_access_tokens(
                    token_digest, subject_user_id, label, purpose,
                    created_by_user_id, created_at, expires_at, max_uses
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    token_digest,
                    subject.id,
                    normalized_label[:200],
                    purpose,
                    actor.id,
                    now.isoformat(),
                    expires_at.isoformat(),
                    max_uses,
                ),
            )
            access_id = int(cursor.lastrowid)
            connection.execute(
                """
                INSERT INTO auth_audit_events(actor_id, action, target_user_id, reason, result, created_at)
                VALUES (?, 'create_temporary_access', ?, ?, 'success', ?)
                """,
                (actor.id, subject.id, normalized_reason[:500], now.isoformat()),
            )
            row = connection.execute(
                "SELECT * FROM temporary_access_tokens WHERE id = ?",
                (access_id,),
            ).fetchone()
            connection.execute("COMMIT")
        assert row is not None
        return IssuedTemporaryAccess(self._row_to_access(row), token)

    def list_access(self) -> list[TemporaryAccess]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM temporary_access_tokens ORDER BY id DESC"
            ).fetchall()
        return [self._row_to_access(row) for row in rows]

    def exchange(self, token: str, auth: LocalAuthProvider) -> tuple[User, Session, TemporaryAccess] | None:
        if not token.startswith(TOKEN_PREFIX) or len(token) < len(TOKEN_PREFIX) + 32:
            return None
        digest = self.digest(token)
        now = datetime.now(UTC)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT t.*, u.username, u.role, u.is_active
                FROM temporary_access_tokens t
                JOIN users u ON u.id = t.subject_user_id
                WHERE t.token_digest = ?
                """,
                (digest,),
            ).fetchone()
            if row is None:
                connection.execute("ROLLBACK")
                return None
            expires_at = datetime.fromisoformat(row["expires_at"])
            if (
                row["revoked_at"] is not None
                or expires_at <= now
                or int(row["uses_count"]) >= int(row["max_uses"])
                or not bool(row["is_active"])
                or UserRole(row["role"]) is UserRole.ADMIN
            ):
                connection.execute("ROLLBACK")
                return None

            user = User(
                int(row["subject_user_id"]),
                row["username"],
                UserRole(row["role"]),
                True,
            )
            session_token = secrets.token_urlsafe(32)
            session_hash = self.digest(session_token)
            session_expires_at = min(now + auth.session_ttl, expires_at)
            connection.execute(
                "INSERT INTO sessions(token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (session_hash, user.id, session_expires_at.isoformat()),
            )
            connection.execute(
                """
                UPDATE temporary_access_tokens
                SET uses_count = uses_count + 1, last_used_at = ?
                WHERE id = ?
                """,
                (now.isoformat(), int(row["id"])),
            )
            connection.execute(
                """
                INSERT INTO temporary_access_sessions(session_token_hash, temporary_access_id, created_at)
                VALUES (?, ?, ?)
                """,
                (session_hash, int(row["id"]), now.isoformat()),
            )
            updated = connection.execute(
                "SELECT * FROM temporary_access_tokens WHERE id = ?",
                (int(row["id"]),),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO auth_audit_events(actor_id, action, target_user_id, reason, result, created_at)
                VALUES (?, 'exchange_temporary_access', ?, 'passwordless entry', 'success', ?)
                """,
                (user.id, user.id, now.isoformat()),
            )
            connection.execute("COMMIT")
        assert updated is not None
        return user, Session(session_token, user.id, session_expires_at), self._row_to_access(updated)

    def revoke(self, access_id: int, *, actor: User, reason: str) -> bool:
        normalized_reason = reason.strip()
        if not normalized_reason:
            raise ValueError("reason is required")
        now = datetime.now(UTC)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT subject_user_id, revoked_at FROM temporary_access_tokens WHERE id = ?",
                (access_id,),
            ).fetchone()
            if row is None:
                connection.execute("ROLLBACK")
                return False
            if row["revoked_at"] is None:
                connection.execute(
                    """
                    UPDATE temporary_access_tokens
                    SET revoked_at = ?, revoked_by_user_id = ?, revocation_reason = ?
                    WHERE id = ?
                    """,
                    (now.isoformat(), actor.id, normalized_reason[:500], access_id),
                )
                connection.execute(
                    """
                    UPDATE sessions SET revoked_at = ?
                    WHERE token_hash IN (
                        SELECT session_token_hash FROM temporary_access_sessions
                        WHERE temporary_access_id = ?
                    ) AND revoked_at IS NULL
                    """,
                    (now.isoformat(), access_id),
                )
                connection.execute(
                    """
                    INSERT INTO auth_audit_events(actor_id, action, target_user_id, reason, result, created_at)
                    VALUES (?, 'revoke_temporary_access', ?, ?, 'success', ?)
                    """,
                    (actor.id, int(row["subject_user_id"]), normalized_reason[:500], now.isoformat()),
                )
            connection.execute("COMMIT")
        return True
