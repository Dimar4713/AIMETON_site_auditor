from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.auth import PasswordHasher, UserRole
from app.session_resolution import (
    SessionFailure,
    TypedLocalAuthProvider,
    TypedSQLiteUserRepository,
)


def make_auth(tmp_path):
    repository = TypedSQLiteUserRepository(tmp_path / "auth.sqlite3")
    password = "correct-horse-battery-staple"
    user = repository.create_user(
        "User@Example.COM ",
        PasswordHasher().hash(password),
        UserRole.USER,
    )
    return repository, TypedLocalAuthProvider(repository), user, password


def test_missing_and_unknown_tokens_are_unauthenticated(tmp_path) -> None:
    _repository, auth, _user, _password = make_auth(tmp_path)
    assert auth.resolve_session_typed("").failure is SessionFailure.UNAUTHENTICATED
    assert auth.resolve_session_typed("unknown").failure is SessionFailure.UNAUTHENTICATED


def test_revoked_session_has_typed_reason(tmp_path) -> None:
    _repository, auth, user, _password = make_auth(tmp_path)
    session = auth.create_session(user)
    auth.revoke_session(session.token)
    assert auth.resolve_session_typed(session.token).failure is SessionFailure.SESSION_REVOKED


def test_expired_session_has_typed_reason(tmp_path) -> None:
    repository, _auth, user, _password = make_auth(tmp_path)
    auth = TypedLocalAuthProvider(repository, session_ttl=timedelta(seconds=-1))
    session = auth.create_session(user)
    assert auth.resolve_session_typed(session.token).failure is SessionFailure.SESSION_EXPIRED


def test_blocked_user_is_enforced_server_side(tmp_path) -> None:
    repository, auth, user, _password = make_auth(tmp_path)
    session = auth.create_session(user)
    repository.set_active(user.id, False)
    result = auth.resolve_session_typed(session.token)
    assert result.failure in {
        SessionFailure.USER_BLOCKED,
        SessionFailure.SESSION_REVOKED,
    }
    assert result.user is None


def test_valid_session_returns_safe_user_projection(tmp_path) -> None:
    _repository, auth, user, _password = make_auth(tmp_path)
    session = auth.create_session(user)
    result = auth.resolve_session_typed(session.token)
    assert result.failure is None
    assert result.user == user
    assert not hasattr(result.user, "password_hash")
    assert datetime.now(UTC) < session.expires_at
