from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hmac
import os
from pathlib import Path
import secrets

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.admin_users import AdminSQLiteUserRepository
from app.auth import AuthProvider, User, UserRole
from app.auth_boundary import RoleAdminPolicy
from app.session_resolution import SessionFailure, SessionResolution, TypedLocalAuthProvider
from app.temporary_access import TemporaryAccess, TemporaryAccessRepository


SESSION_COOKIE = "aimeton_session"
CSRF_COOKIE = "aimeton_csrf"
CSRF_HEADER = "X-CSRF-Token"
router = APIRouter(tags=["auth"])


def _database_path() -> Path:
    return Path(os.getenv("AIMETON_AUTH_DB", "data/auth.sqlite3"))


def _cookie_secure() -> bool:
    return os.getenv("AIMETON_COOKIE_SECURE", "true").lower() not in {"0", "false", "no"}


def get_auth_provider() -> TypedLocalAuthProvider:
    path = _database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return TypedLocalAuthProvider(AdminSQLiteUserRepository(path))


def get_temporary_access_repository() -> TemporaryAccessRepository:
    path = _database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return TemporaryAccessRepository(path)


def _resolve_session(auth: AuthProvider, token: str) -> SessionResolution:
    typed_resolver = getattr(auth, "resolve_session_typed", None)
    if callable(typed_resolver):
        return typed_resolver(token)
    user = auth.resolve_session(token)
    return SessionResolution(user=user) if user else SessionResolution(failure=SessionFailure.UNAUTHENTICATED)


def current_user(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    auth: AuthProvider = Depends(get_auth_provider),
) -> User:
    resolution = _resolve_session(auth, session_token or "")
    if resolution.failure is not None or resolution.user is None:
        raise HTTPException(status_code=401, detail={"reason": "unauthenticated"})
    return resolution.user


def require_admin(user: User = Depends(current_user)) -> User:
    if not RoleAdminPolicy().allows_admin_operation(user):
        raise HTTPException(status_code=403, detail={"reason": "role_forbidden"})
    return user


def _require_csrf(cookie_token: str | None, header_token: str | None) -> None:
    if not cookie_token or not header_token or not hmac.compare_digest(cookie_token, header_token):
        raise HTTPException(status_code=403, detail={"reason": "csrf_failed"})


class TokenLoginRequest(BaseModel):
    token: str = Field(min_length=32, max_length=512)


class TemporaryAccessCreateRequest(BaseModel):
    subject_user_id: int = Field(gt=0)
    label: str = Field(min_length=1, max_length=200)
    purpose: str = Field(pattern="^(agent|marketing_demo|support|other)$")
    ttl_minutes: int = Field(ge=5, le=43200)
    max_uses: int = Field(ge=1, le=1000)
    reason: str = Field(min_length=1, max_length=500)


class TemporaryAccessRevokeRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class TemporaryAccessResponse(BaseModel):
    id: int
    subject_user_id: int
    label: str
    purpose: str
    created_at: str
    expires_at: str
    max_uses: int
    uses_count: int
    last_used_at: str | None
    revoked_at: str | None

    @classmethod
    def from_access(cls, access: TemporaryAccess) -> "TemporaryAccessResponse":
        return cls(
            id=access.id,
            subject_user_id=access.subject_user_id,
            label=access.label,
            purpose=access.purpose,
            created_at=access.created_at.isoformat(),
            expires_at=access.expires_at.isoformat(),
            max_uses=access.max_uses,
            uses_count=access.uses_count,
            last_used_at=access.last_used_at.isoformat() if access.last_used_at else None,
            revoked_at=access.revoked_at.isoformat() if access.revoked_at else None,
        )


class IssuedTemporaryAccessResponse(TemporaryAccessResponse):
    token: str
    magic_link_fragment: str


class TokenLoginResponse(BaseModel):
    id: int
    username: str
    role: UserRole
    is_active: bool
    temporary_access_id: int
    temporary_access_expires_at: str
    remaining_uses: int


@router.post("/token-login", response_model=TokenLoginResponse)
def token_login(
    payload: TokenLoginRequest,
    response: Response,
    existing_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    auth: TypedLocalAuthProvider = Depends(get_auth_provider),
    temporary_access: TemporaryAccessRepository = Depends(get_temporary_access_repository),
):
    exchanged = temporary_access.exchange(payload.token, auth)
    if exchanged is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"reason": "unauthenticated"})
    user, session, access = exchanged
    auth.revoke_session(existing_session or "")
    csrf_token = secrets.token_urlsafe(32)
    max_age = max(1, int((session.expires_at - datetime.now(UTC)).total_seconds()))
    secure = _cookie_secure()
    response.set_cookie(SESSION_COOKIE, session.token, httponly=True, secure=secure, samesite="strict", max_age=max_age, path="/")
    response.set_cookie(CSRF_COOKIE, csrf_token, httponly=False, secure=secure, samesite="strict", max_age=max_age, path="/")
    return TokenLoginResponse(
        id=user.id,
        username=user.username,
        role=user.role,
        is_active=user.is_active,
        temporary_access_id=access.id,
        temporary_access_expires_at=access.expires_at.isoformat(),
        remaining_uses=max(0, access.max_uses - access.uses_count),
    )


@router.post("/admin/temporary-access-tokens", response_model=IssuedTemporaryAccessResponse, status_code=201)
def create_temporary_access(
    payload: TemporaryAccessCreateRequest,
    admin: User = Depends(require_admin),
    csrf_cookie: str | None = Cookie(default=None, alias=CSRF_COOKIE),
    csrf_header: str | None = Header(default=None, alias=CSRF_HEADER),
    auth: TypedLocalAuthProvider = Depends(get_auth_provider),
    temporary_access: TemporaryAccessRepository = Depends(get_temporary_access_repository),
):
    _require_csrf(csrf_cookie, csrf_header)
    subject = auth.repository.get_by_id(payload.subject_user_id)
    if subject is None:
        raise HTTPException(status_code=404, detail={"reason": "user_not_found"})
    try:
        issued = temporary_access.issue(
            subject=subject,
            actor=admin,
            label=payload.label,
            purpose=payload.purpose,
            expires_at=datetime.now(UTC) + timedelta(minutes=payload.ttl_minutes),
            max_uses=payload.max_uses,
            reason=payload.reason,
        )
    except PermissionError:
        raise HTTPException(status_code=403, detail={"reason": "temporary_access_forbidden"})
    except ValueError:
        raise HTTPException(status_code=422, detail={"reason": "invalid_temporary_access"})
    metadata = TemporaryAccessResponse.from_access(issued.access).model_dump()
    return IssuedTemporaryAccessResponse(
        **metadata,
        token=issued.token,
        magic_link_fragment=f"#access_token={issued.token}",
    )


@router.get("/admin/temporary-access-tokens", response_model=list[TemporaryAccessResponse])
def list_temporary_access(
    _admin: User = Depends(require_admin),
    temporary_access: TemporaryAccessRepository = Depends(get_temporary_access_repository),
):
    return [TemporaryAccessResponse.from_access(item) for item in temporary_access.list_access()]


@router.post("/admin/temporary-access-tokens/{access_id}/revoke", status_code=204)
def revoke_temporary_access(
    access_id: int,
    payload: TemporaryAccessRevokeRequest,
    admin: User = Depends(require_admin),
    csrf_cookie: str | None = Cookie(default=None, alias=CSRF_COOKIE),
    csrf_header: str | None = Header(default=None, alias=CSRF_HEADER),
    temporary_access: TemporaryAccessRepository = Depends(get_temporary_access_repository),
):
    _require_csrf(csrf_cookie, csrf_header)
    if not temporary_access.revoke(access_id, actor=admin, reason=payload.reason):
        raise HTTPException(status_code=404, detail={"reason": "temporary_access_not_found"})
