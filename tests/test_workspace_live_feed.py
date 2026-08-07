from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_workspace_uses_bounded_visible_page_polling() -> None:
    script = (ROOT / "static" / "workspace.js").read_text(encoding="utf-8")

    assert "POLL_INTERVAL_MS = 15000" in script
    assert "LIVE_RECORD_LIMIT = 20" in script
    assert "document.visibilityState === 'visible'" in script
    assert "loadMissions({silent: true})" in script


def test_workspace_projects_latest_sanitized_operational_status() -> None:
    script = (ROOT / "static" / "workspace.js").read_text(encoding="utf-8")

    assert "/records`" in script
    assert "latestOperationalStatus" in script
    assert "eventLabel" in script
    assert "heartbeatLabel" in script
    assert "heartbeat_status" in script
    assert "observation.stalled" in script
    assert "input_snapshot" in script  # request input only
    assert "technical_snapshot" not in script
    assert "chain-of-thought" not in script


def test_workspace_reports_real_bounded_runtime_progress() -> None:
    script = (ROOT / "static" / "workspace.js").read_text(encoding="utf-8")

    assert "site_fetch_started" in script
    assert "site_fetch_completed" in script
    assert "analysis_completed" in script
    assert "analysis_failed" in script
    assert "Миссия принята:" in script
    assert "mission.state === 'blocked'" not in script
    assert "рабочий контур пока не настроен" not in script
