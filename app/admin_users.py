from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from app.auth import PasswordHasher, User, UserRole
from app.session_resolution import TypedSQLiteUserRepository


@dataclass(frozen=True)
class AdminAuditEvent:
    id: int
    actor_id: int
    action: str
    target_user_id: int | None
    reason: str
    result: str
    created_at: str


class AdminUserRepository(Protocol):
    def create_user(self, username: str, password_hash: str, role: UserRole) -> User: ...
    def get_by_id(self, user_id: int) -> User | None: ...
    def list_users(self) -> list[User]: ...
    def set_active(self, user_id: int, active: bool) -> None: ...
    def update_password(self, user_id: int, password_hash: str) -> None: ...
    def add_audit_event(self, actor_id: int, action: str, target_user_id: int | None, reason: str, result: str) -> None: ...
    def list_audit_events(self, limit: int = 100) -> list[AdminAuditEvent]: ...


class AdminSQLiteUserRepository(TypedSQLiteUserRepository):
    def _initialize(self) -> None:
        super()._initialize()
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    target_user_id INTEGER,
                    reason TEXT NOT NULL,
                    result TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def list_users(self) -> list[User]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, username, role, is_active FROM users ORDER BY id"
            ).fetchall()
        return [User(row["id"], row["username"], UserRole(row["role"]), bool(row["is_active"])) for row in rows]

    def update_password(self, user_id: int, password_hash: str) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (password_hash, user_id),
            )
            if cursor.rowcount != 1:
                raise LookupError("user not found")
            connection.execute(
                "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                (datetime.now(UTC).isoformat(), user_id),
            )

    def add_audit_event(self, actor_id: int, action: str, target_user_id: int | None, reason: str, result: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO auth_audit_events(actor_id, action, target_user_id, reason, result, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (actor_id, action, target_user_id, reason.strip()[:500], result, datetime.now(UTC).isoformat()),
            )

    def list_audit_events(self, limit: int = 100) -> list[AdminAuditEvent]:
        safe_limit = max(1, min(limit, 1000))
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT id, actor_id, action, target_user_id, reason, result, created_at
                FROM auth_audit_events ORDER BY id DESC LIMIT ?""",
                (safe_limit,),
            ).fetchall()
        return [AdminAuditEvent(**dict(row)) for row in rows]


@dataclass(frozen=True)
class AdminOperation:
    actor: User
    reason: str

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError("reason is required")


class AdminUserService:
    def __init__(self, repository: AdminUserRepository, hasher: PasswordHasher | None = None):
        self.repository = repository
        self.hasher = hasher or PasswordHasher()

    def list_users(self) -> list[User]:
        return self.repository.list_users()

    def list_audit_events(self, limit: int = 100) -> list[AdminAuditEvent]:
        return self.repository.list_audit_events(limit)

    def create_user(self, operation: AdminOperation, username: str, password: str, role: UserRole) -> User:
        try:
            user = self.repository.create_user(username, self.hasher.hash(password), role)
        except Exception:
            self.repository.add_audit_event(operation.actor.id, "create_user", None, operation.reason, "failed")
            raise
        self.repository.add_audit_event(operation.actor.id, "create_user", user.id, operation.reason, "success")
        return user

    def set_active(self, operation: AdminOperation, user_id: int, active: bool) -> User:
        target = self.repository.get_by_id(user_id)
        if target is None:
            self.repository.add_audit_event(operation.actor.id, "set_active", user_id, operation.reason, "not_found")
            raise LookupError("user not found")
        if target.id == operation.actor.id and not active:
            self.repository.add_audit_event(operation.actor.id, "set_active", user_id, operation.reason, "self_block_denied")
            raise PermissionError("admin cannot block own account")
        self.repository.set_active(user_id, active)
        self.repository.add_audit_event(operation.actor.id, "set_active", user_id, operation.reason, "success")
        updated = self.repository.get_by_id(user_id)
        assert updated is not None
        return updated

    def reset_password(self, operation: AdminOperation, user_id: int, password: str) -> None:
        if self.repository.get_by_id(user_id) is None:
            self.repository.add_audit_event(operation.actor.id, "reset_password", user_id, operation.reason, "not_found")
            raise LookupError("user not found")
        self.repository.update_password(user_id, self.hasher.hash(password))
        self.repository.add_audit_event(operation.actor.id, "reset_password", user_id, operation.reason, "success")
