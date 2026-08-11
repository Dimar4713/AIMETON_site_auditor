from pathlib import Path


STATIC = Path(__file__).resolve().parents[1] / "static"


def test_legacy_result_compat_is_loaded_after_workspace() -> None:
    index = (STATIC / "index.html").read_text(encoding="utf-8")
    assert "/static/workspace-legacy-result-compat.js" in index
    assert index.index("/static/business-audit-workspace.js") < index.index("/static/workspace-legacy-result-compat.js")


def test_async_completion_hides_only_legacy_report_body() -> None:
    script = (STATIC / "workspace-legacy-result-compat.js").read_text(encoding="utf-8")
    assert "aimeton:analysis-complete" in script
    assert "#resultInner" in script
    assert "setAttribute('hidden', '')" in script
    assert "#result'" not in script
    assert "#chat" not in script
    assert "fetch(" not in script
    assert "setInterval(" not in script


def test_exports_and_history_remain_owned_by_existing_app() -> None:
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "/api/export/analysis.md" in app
    assert "/api/export/analysis.docx" in app
    assert "exportPDF" in app
    assert "saveToHistory" in app
    assert "renderChatSession" in app
