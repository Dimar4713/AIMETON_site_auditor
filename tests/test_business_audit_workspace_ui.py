from pathlib import Path


STATIC = Path(__file__).resolve().parents[1] / "static"


def test_workspace_assets_are_connected() -> None:
    index = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'id="businessAuditWorkspace"' in index
    assert "/static/business-audit-workspace.css" in index
    assert "/static/business-audit-workspace.js" in index
    assert index.index("/static/live-analysis.js") < index.index("/static/business-audit-workspace.js")


def test_workspace_uses_event_bridge_not_second_polling_loop() -> None:
    script = (STATIC / "business-audit-workspace.js").read_text(encoding="utf-8")
    for name in (
        "aimeton:analysis-started",
        "aimeton:analysis-update",
        "aimeton:analysis-complete",
    ):
        assert name in script
    assert "/api/analyze/start" not in script
    assert "status_url" not in script
    assert "events_url" not in script
    assert "setInterval(" not in script
    assert "fetch(" not in script


def test_workspace_uses_canonical_customer_term_and_defensive_rendering() -> None:
    script = (STATIC / "business-audit-workspace.js").read_text(encoding="utf-8")
    assert "Анализ бизнеса по 16 зонам" in script
    assert "Бизнес-машина AIMETON 4×4" not in script
    assert "Array.isArray" in script
    assert "undefined" not in script
    assert "progress_percent" not in script.lower()
    assert "percentage" not in script.lower()


def test_existing_integrations_remain_available() -> None:
    index = (STATIC / "index.html").read_text(encoding="utf-8")
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    service_catalog = (STATIC / "service-catalog.js").read_text(encoding="utf-8")

    assert 'id="authGate"' in index
    assert 'id="loginForm"' in index
    assert 'id="chatForm"' in index
    assert "/api/chat" in app
    assert "/api/export/analysis.md" in app
    assert "/api/export/analysis.docx" in app
    assert "/api/company-intelligence" in service_catalog
    assert "/api/hunt" in service_catalog


def test_workspace_styles_are_namespaced_and_responsive() -> None:
    styles = (STATIC / "business-audit-workspace.css").read_text(encoding="utf-8")
    assert ".business-audit-workspace" in styles
    assert ".baw-" in styles
    assert "@media(max-width:760px)" in styles
