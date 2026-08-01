from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.auth import LocalAuthProvider, SQLiteUserRepository, User, UserRole, bootstrap_admin_from_env


SESSION_COOKIE = "aimeton_session"
router = APIRouter(prefix="/api/auth", tags=["auth"])


def _database_path() -> Path:
    return Path(os.getenv("AIMETON_AUTH_DB", "data/auth.sqlite3"))


def get_auth_provider() -> LocalAuthProvider:
    path = _database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    repository = SQLiteUserRepository(path)
    bootstrap_admin_from_env(repository)
    return LocalAuthProvider(repository)


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


def current_user(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    auth: LocalAuthProvider = Depends(get_auth_provider),
) -> User:
    user = auth.resolve_session(session_token or "")
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role is not UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin role required")
    return user


@router.post("/login", response_model=UserResponse)
def login(payload: LoginRequest, response: Response, auth: LocalAuthProvider = Depends(get_auth_provider)):
    user = auth.authenticate(payload.username, payload.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    session = auth.create_session(user)
    response.set_cookie(
        SESSION_COOKIE,
        session.token,
        httponly=True,
        secure=os.getenv("AIMETON_COOKIE_SECURE", "true").lower() not in {"0", "false", "no"},
        samesite="strict",
        max_age=max(1, int((session.expires_at.timestamp()))),
        path="/",
    )
    return UserResponse.from_user(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    auth: LocalAuthProvider = Depends(get_auth_provider),
):
    auth.revoke_session(session_token or "")
    response.delete_cookie(SESSION_COOKIE, path="/")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(current_user)):
    return UserResponse.from_user(user)


@router.get("/admin/ping")
def admin_ping(_user: User = Depends(require_admin)):
    return {"status": "ok", "role": "admin"}
