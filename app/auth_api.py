from __future__ import annotations

from datetime import UTC, datetime
import hmac
import os
from pathlib import Path
import secrets

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.auth import AuthProvider, User, UserRole, bootstrap_admin_from_env
from app.auth_boundary import AdminPolicy, RoleAdminPolicy
from app.session_resolution import (
    SessionFailure,
    SessionResolution,
    TypedLocalAuthProvider,
    TypedSQLiteUserRepository,
)


SESSION_COOKIE = "aimeton_session"
CSRF_COOKIE = "aimeton_csrf"
CSRF_HEADER = "X-CSRF-Token"
router = APIRouter(prefix="/api/auth", tags=["auth"])


def _database_path() -> Path:
    return Path(os.getenv("AIMETON_AUTH_DB", "data/auth.sqlite3"))


def _cookie_secure() -> bool:
    return os.getenv("AIMETON_COOKIE_SECURE", "true").lower() not in {
        "0",
        "false",
        "no",
    }


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


def _resolve_session(auth: AuthProvider, token: str) -> SessionResolution:
    """Prefer typed providers while preserving compatibility with injected legacy fakes."""
    typed_resolver = getattr(auth, "resolve_session_typed", None)
    if callable(typed_resolver):
        return typed_resolver(token)
    user = auth.resolve_session(token)
    if user is None:
        return SessionResolution(failure=SessionFailure.UNAUTHENTICATED)
    return SessionResolution(user=user)


def _require_csrf(cookie_token: str | None, header_token: str | None) -> None:
    if (
        not cookie_token
        or not header_token
        or not hmac.compare_digest(cookie_token, header_token)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"reason": "csrf_failed"},
        )


def current_user(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    auth: AuthProvider = Depends(get_auth_provider),
) -> User:
    resolution = _resolve_session(auth, session_token or "")
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
    existing_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    auth: AuthProvider = Depends(get_auth_provider),
):
    user = auth.authenticate(payload.username, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"reason": "unauthenticated"},
        )

    # Prevent session fixation: any session presented before login is revoked,
    # then a fresh server-side session and CSRF token are issued.
    auth.revoke_session(existing_session or "")
    session = auth.create_session(user)
    csrf_token = secrets.token_urlsafe(32)
    max_age = max(1, int((session.expires_at - datetime.now(UTC)).total_seconds()))
    secure = _cookie_secure()
    response.set_cookie(
        SESSION_COOKIE,
        session.token,
        httponly=True,
        secure=secure,
        samesite="strict",
        max_age=max_age,
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        httponly=False,
        secure=secure,
        samesite="strict",
        max_age=max_age,
        path="/",
    )
    return UserResponse.from_user(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    csrf_cookie: str | None = Cookie(default=None, alias=CSRF_COOKIE),
    csrf_header: str | None = Header(default=None, alias=CSRF_HEADER),
    auth: AuthProvider = Depends(get_auth_provider),
):
    _require_csrf(csrf_cookie, csrf_header)
    auth.revoke_session(session_token or "")
    secure = _cookie_secure()
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        secure=secure,
        httponly=True,
        samesite="strict",
    )
    response.delete_cookie(
        CSRF_COOKIE,
        path="/",
        secure=secure,
        httponly=False,
        samesite="strict",
    )


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(current_user)):
    return UserResponse.from_user(user)


@router.get("/admin/ping")
def admin_ping(_user: User = Depends(require_admin)):
    return {"status": "ok", "role": "admin"}
