from pathlib import Path


def test_admin_workspace_contains_provider_waterfall_panel() -> None:
    html = Path("static/admin-workspace.html").read_text(encoding="utf-8")
    assert 'id="trace-waterfall-form"' in html
    assert 'id="trace-mission-id"' in html
    assert 'id="trace-attempt-id"' in html
    assert 'id="admin-trace-waterfall"' in html


def test_admin_waterfall_client_uses_safe_read_only_boundary() -> None:
    source = Path("static/admin-workspace.js").read_text(encoding="utf-8")
    assert "/api/admin/missions/" in source
    assert "/provider-waterfall" in source
    assert "encodeURIComponent(missionId)" in source
    assert "encodeURIComponent(attemptId)" in source
    assert "used_in_report" in source
    for forbidden in (
        "password_hash",
        "authorization",
        "api_key",
        "raw_payload",
        "runtime-core.sqlite3",
        "storage_path",
    ):
        assert forbidden not in source.lower()
