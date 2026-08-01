from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from app.auth import LocalAuthProvider, SQLiteUserRepository, User, UserRole


class SessionFailure(StrEnum):
    UNAUTHENTICATED = "unauthenticated"
    SESSION_EXPIRED = "session_expired"
    SESSION_REVOKED = "session_revoked"
    USER_BLOCKED = "user_blocked"


@dataclass(frozen=True)
class SessionResolution:
    user: User | None = None
    failure: SessionFailure | None = None

    def __post_init__(self) -> None:
        if (self.user is None) == (self.failure is None):
            raise ValueError("resolution must contain exactly one of user or failure")


class TypedSQLiteUserRepository(SQLiteUserRepository):
    """SQLite adapter that preserves the reason a session cannot be used."""

    def resolve_session_typed(
        self,
        token_hash: str,
        now: datetime,
    ) -> SessionResolution:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT u.id, u.username, u.role, u.is_active,
                       s.expires_at, s.revoked_at
                FROM sessions s JOIN users u ON u.id = s.user_id
                WHERE s.token_hash = ?
                """,
                (token_hash,),
            ).fetchone()
        if row is None:
            return SessionResolution(failure=SessionFailure.UNAUTHENTICATED)
        if row["revoked_at"] is not None:
            return SessionResolution(failure=SessionFailure.SESSION_REVOKED)
        if datetime.fromisoformat(row["expires_at"]) <= now:
            return SessionResolution(failure=SessionFailure.SESSION_EXPIRED)
        if not bool(row["is_active"]):
            return SessionResolution(failure=SessionFailure.USER_BLOCKED)
        return SessionResolution(
            user=User(
                row["id"],
                row["username"],
                UserRole(row["role"]),
                True,
            )
        )


class TypedLocalAuthProvider(LocalAuthProvider):
    repository: TypedSQLiteUserRepository

    def __init__(self, repository: TypedSQLiteUserRepository, **kwargs: object):
        super().__init__(repository, **kwargs)
        self.repository = repository

    def resolve_session_typed(self, token: str) -> SessionResolution:
        if not token:
            return SessionResolution(failure=SessionFailure.UNAUTHENTICATED)
        return self.repository.resolve_session_typed(
            self._token_hash(token),
            datetime.now(UTC),
        )

    def resolve_session(self, token: str) -> User | None:
        return self.resolve_session_typed(token).user
