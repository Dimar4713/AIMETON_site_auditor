from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.auth import PasswordHasher, User, UserRole


class AdminUserRepository(Protocol):
    def create_user(self, username: str, password_hash: str, role: UserRole) -> User: ...
    def get_by_id(self, user_id: int) -> User | None: ...
    def list_users(self) -> list[User]: ...
    def set_active(self, user_id: int, active: bool) -> None: ...
    def update_password(self, user_id: int, password_hash: str) -> None: ...
    def add_audit_event(self, actor_id: int, action: str, target_user_id: int | None, reason: str, result: str) -> None: ...


@dataclass(frozen=True)
class AdminOperation:
    actor: User
    reason: str


class AdminUserService:
    def __init__(self, repository: AdminUserRepository, hasher: PasswordHasher | None = None):
        self.repository = repository
        self.hasher = hasher or PasswordHasher()

    def list_users(self) -> list[User]:
        return self.repository.list_users()

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
