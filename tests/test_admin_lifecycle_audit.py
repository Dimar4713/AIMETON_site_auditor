from pathlib import Path

from app.admin_users import AdminSQLiteUserRepository


def test_admin_audit_events_are_persistent_and_sanitized(tmp_path: Path) -> None:
    path = tmp_path / "auth.sqlite3"
    repository = AdminSQLiteUserRepository(path)
    repository.add_audit_event(1, "set_active", 2, "approved maintenance", "success")

    reopened = AdminSQLiteUserRepository(path)
    events = reopened.list_audit_events()

    assert len(events) == 1
    assert events[0].action == "set_active"
    assert events[0].target_user_id == 2
    assert events[0].reason == "approved maintenance"
    assert events[0].result == "success"
    assert not hasattr(events[0], "password_hash")
    assert not hasattr(events[0], "session_token")


def test_admin_workspace_uses_csrf_lifecycle_and_safe_audit_projection() -> None:
    source = Path("static/admin-workspace.js").read_text(encoding="utf-8")
    html = Path("static/admin-workspace.html").read_text(encoding="utf-8")

    assert "/api/auth/admin/users/${user.id}/state" in source
    assert "X-CSRF-Token" in source
    assert "aimeton_csrf" in source
    assert "/api/auth/admin/audit-events?limit=100" in source
    assert "admin-audit" in html

    for forbidden in (
        "password_hash",
        "aimeton_session",
        "storage_path",
        "signed_url",
        "technical_snapshot",
    ):
        assert forbidden not in source
        assert forbidden not in html
