from datetime import timedelta

import pytest

from app.auth import LocalAuthProvider, PasswordHasher, SQLiteUserRepository, UserRole


@pytest.fixture
def repository(tmp_path):
    return SQLiteUserRepository(tmp_path / "auth.sqlite3")


def create_user(repository, username="user", password="correct horse battery", role=UserRole.USER):
    hasher = PasswordHasher()
    return repository.create_user(username, hasher.hash(password), role)


def test_password_hash_does_not_expose_password():
    encoded = PasswordHasher().hash("correct horse battery")
    assert "correct horse battery" not in encoded
    assert encoded.startswith("scrypt$")


def test_password_hash_rejects_short_password():
    with pytest.raises(ValueError):
        PasswordHasher().hash("short")


def test_authenticate_and_session_survive_repository_restart(repository, tmp_path):
    user = create_user(repository)
    auth = LocalAuthProvider(repository)
    authenticated = auth.authenticate("USER", "correct horse battery")
    assert authenticated == user

    session = auth.create_session(user)
    restarted_repository = SQLiteUserRepository(tmp_path / "auth.sqlite3")
    restarted_auth = LocalAuthProvider(restarted_repository)
    assert restarted_auth.resolve_session(session.token) == user


def test_wrong_password_does_not_create_identity(repository):
    create_user(repository)
    auth = LocalAuthProvider(repository)
    assert auth.authenticate("user", "wrong password value") is None


def test_logout_revokes_session(repository):
    user = create_user(repository)
    auth = LocalAuthProvider(repository)
    session = auth.create_session(user)
    auth.revoke_session(session.token)
    assert auth.resolve_session(session.token) is None


def test_blocking_user_revokes_existing_sessions(repository):
    user = create_user(repository)
    auth = LocalAuthProvider(repository)
    session = auth.create_session(user)
    repository.set_active(user.id, False)
    assert auth.resolve_session(session.token) is None
    assert auth.authenticate("user", "correct horse battery") is None


def test_expired_session_is_rejected(repository):
    user = create_user(repository)
    auth = LocalAuthProvider(repository, session_ttl=timedelta(seconds=-1))
    session = auth.create_session(user)
    assert auth.resolve_session(session.token) is None


def test_roles_are_typed(repository):
    admin = create_user(repository, username="admin", role=UserRole.ADMIN)
    user = create_user(repository, username="analyst", role=UserRole.USER)
    assert admin.role is UserRole.ADMIN
    assert user.role is UserRole.USER
