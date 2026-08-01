from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.auth import User, UserRole, bootstrap_admin_from_env
from app.auth_boundary import AdminPolicy, RoleAdminPolicy
from app.session_resolution import (
    SessionFailure,
    TypedLocalAuthProvider,
    TypedSQLiteUserRepository,
)


SESSION_COOKIE = "aimeton_session"
router = APIRouter(prefix="/api/auth", tags=["auth"])


def _database_path() -> Path:
    return Path(os.getenv("AIMETON_AUTH_DB", "data/auth.sqlite3"))


def get_auth_provider() -> TypedLocalAuthProvider:
    path = _database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    repository = TypedSQLiteUserRepository(path)
    bootstrap_admin_from_env(repository)
    return TypedLocalAuthProvider(repository)


def get_admin_policy() -> AdminPolicy:
    return RoleAdminPolicy()


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=1024)


class UserResponse(BaseModel):
    id: int
    username: str
    role: UserRole

    @classmethod
    def from_user(cls, user: User) -> "UserResponse":
        return cls(id=user.id, username=user.username, role=user.role)


def _auth_error(reason: SessionFailure) -> HTTPException:
    if reason is SessionFailure.USER_BLOCKED:
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"reason": reason.value},
        )
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"reason": reason.value},
    )


def current_user(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    auth: TypedLocalAuthProvider = Depends(get_auth_provider),
) -> User:
    resolution = auth.resolve_session_typed(session_token or "")
    if resolution.failure is not None:
        raise _auth_error(resolution.failure)
    assert resolution.user is not None
    return resolution.user


def require_admin(
    user: User = Depends(current_user),
    policy: AdminPolicy = Depends(get_admin_policy),
) -> User:
    if not policy.allows_admin_operation(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"reason": "role_forbidden"},
        )
    return user


@router.post("/login", response_model=UserResponse)
def login(
    payload: LoginRequest,
    response: Response,
    auth: TypedLocalAuthProvider = Depends(get_auth_provider),
):
    user = auth.authenticate(payload.username, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"reason": "unauthenticated"},
        )
    session = auth.create_session(user)
    max_age = max(1, int((session.expires_at - datetime.now(UTC)).total_seconds()))
    response.set_cookie(
        SESSION_COOKIE,
        session.token,
        httponly=True,
        secure=os.getenv("AIMETON_COOKIE_SECURE", "true").lower()
        not in {"0", "false", "no"},
        samesite="strict",
        max_age=max_age,
        path="/",
    )
    return UserResponse.from_user(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    auth: TypedLocalAuthProvider = Depends(get_auth_provider),
):
    auth.revoke_session(session_token or "")
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        secure=os.getenv("AIMETON_COOKIE_SECURE", "true").lower()
        not in {"0", "false", "no"},
        httponly=True,
        samesite="strict",
    )


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(current_user)):
    return UserResponse.from_user(user)


@router.get("/admin/ping")
def admin_ping(_user: User = Depends(require_admin)):
    return {"status": "ok", "role": "admin"}
