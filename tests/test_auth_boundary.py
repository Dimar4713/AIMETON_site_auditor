from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.auth import SQLiteUserRepository, User, UserRole
from app.auth_api import require_admin
from app.auth_boundary import RoleAdminPolicy


def user(role: UserRole, *, active: bool = True) -> User:
    return User(id=42, username="tester", role=role, is_active=active)


def test_role_admin_policy_allows_active_admin() -> None:
    policy = RoleAdminPolicy()
    assert policy.allows_admin_operation(user(UserRole.ADMIN)) is True


@pytest.mark.parametrize(
    ("candidate", "expected"),
    [
        (user(UserRole.USER), False),
        (user(UserRole.ADMIN, active=False), False),
        (user(UserRole.USER, active=False), False),
    ],
)
def test_role_admin_policy_denies_non_admin_or_inactive_user(
    candidate: User,
    expected: bool,
) -> None:
    policy = RoleAdminPolicy()
    assert policy.allows_admin_operation(candidate) is expected


def test_require_admin_uses_policy_boundary() -> None:
    admin = user(UserRole.ADMIN)
    assert require_admin(admin, RoleAdminPolicy()) is admin


def test_require_admin_returns_typed_403_for_regular_user() -> None:
    with pytest.raises(HTTPException) as error:
        require_admin(user(UserRole.USER), RoleAdminPolicy())
    assert error.value.status_code == 403
    assert error.value.detail == {"reason": "role_forbidden"}


def test_sqlite_adapter_satisfies_session_repository_shape(tmp_path) -> None:
    repository = SQLiteUserRepository(tmp_path / "auth.sqlite3")
    for method in ("store_session", "resolve_session", "revoke_session"):
        assert callable(getattr(repository, method))
