from __future__ import annotations

import os

import pytest

from app.admin_users import AdminSQLiteUserRepository
from app.auth import UserRole
from app.bootstrap_admin import bootstrap


def test_bootstrap_requires_both_secrets(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("AIMETON_BOOTSTRAP_ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("AIMETON_BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="not configured"):
        bootstrap(tmp_path / "auth.sqlite3")

    monkeypatch.setenv("AIMETON_BOOTSTRAP_ADMIN_USERNAME", "root@example.test")
    with pytest.raises(RuntimeError, match="both bootstrap admin variables"):
        bootstrap(tmp_path / "auth.sqlite3")


def test_bootstrap_is_idempotent_and_does_not_rotate_existing_secret(tmp_path, monkeypatch) -> None:
    database = tmp_path / "auth.sqlite3"
    monkeypatch.setenv("AIMETON_BOOTSTRAP_ADMIN_USERNAME", " Root@Example.TEST ")
    monkeypatch.setenv("AIMETON_BOOTSTRAP_ADMIN_PASSWORD", "first bootstrap secret")

    first_username, first_id = bootstrap(database)
    first_record = AdminSQLiteUserRepository(database).get_by_username(first_username)
    assert first_record is not None
    first_user, first_hash = first_record
    assert first_user.role is UserRole.ADMIN

    monkeypatch.setenv("AIMETON_BOOTSTRAP_ADMIN_PASSWORD", "different secret value")
    second_username, second_id = bootstrap(database)
    second_record = AdminSQLiteUserRepository(database).get_by_username(second_username)
    assert second_record is not None
    _second_user, second_hash = second_record

    assert (second_username, second_id) == (first_username, first_id)
    assert second_hash == first_hash
    assert len(AdminSQLiteUserRepository(database).list_users()) == 1


def test_bootstrap_output_contract_never_contains_password_or_hash(tmp_path, monkeypatch, capsys) -> None:
    secret = "super private bootstrap secret"
    monkeypatch.setenv("AIMETON_BOOTSTRAP_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("AIMETON_BOOTSTRAP_ADMIN_PASSWORD", secret)

    username, user_id = bootstrap(tmp_path / "auth.sqlite3")
    output = f"bootstrap_admin=ok username={username} user_id={user_id}"

    assert secret not in output
    assert "$scrypt$" not in output
    assert os.getenv("AIMETON_BOOTSTRAP_ADMIN_PASSWORD") not in output
