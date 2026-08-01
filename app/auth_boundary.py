from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.auth import AuthProvider, Session, User, UserRepository, UserRole


class SessionRepository(Protocol):
    """Replaceable persistence boundary for server-side sessions."""

    def store_session(self, token_hash: str, user_id: int, expires_at: datetime) -> None: ...

    def resolve_session(self, token_hash: str, now: datetime) -> User | None: ...

    def revoke_session(self, token_hash: str) -> None: ...


class AdminPolicy(Protocol):
    """Authorization boundary used by HTTP and future service adapters."""

    def allows_admin_operation(self, user: User) -> bool: ...


class RoleAdminPolicy:
    """Minimal local policy; replaceable without changing business endpoints."""

    def allows_admin_operation(self, user: User) -> bool:
        return user.is_active and user.role is UserRole.ADMIN


__all__ = [
    "AdminPolicy",
    "AuthProvider",
    "RoleAdminPolicy",
    "Session",
    "SessionRepository",
    "User",
    "UserRepository",
]
