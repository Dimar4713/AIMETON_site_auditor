from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADMIN_API = (ROOT / "app" / "admin_trace_api.py").read_text(encoding="utf-8")
TRACED_GATEWAY = (ROOT / "app" / "search_gateway" / "traced_gateway.py").read_text(encoding="utf-8")
ADMIN_HTML = (ROOT / "static" / "admin-workspace.html").read_text(encoding="utf-8")
ADMIN_JS = (ROOT / "static" / "admin-hunter-trace.js").read_text(encoding="utf-8")


def test_admin_can_list_recent_trace_attempts_without_known_ids() -> None:
    assert '@router.get("/trace/recent-attempts"' in ADMIN_API
    assert "hours: int = Query(default=168" in ADMIN_API
    assert "Depends(require_admin)" in ADMIN_API
    assert "GROUP BY mission_id, attempt_id" in ADMIN_API


def test_search_trace_records_bounded_query_text_without_raw_payload() -> None:
    assert 'operation="query_planned"' in TRACED_GATEWAY
    assert '"query_text": " ".join(request.query.split())[:500]' in TRACED_GATEWAY
    assert '"requested_limit": request.limit' in TRACED_GATEWAY
    for forbidden in ("authorization", "api_key", "cookies", "raw_payload"):
        assert forbidden not in TRACED_GATEWAY.lower()


def test_admin_workspace_loads_recent_trace_browser() -> None:
    assert "/static/admin-hunter-trace.js" in ADMIN_HTML
    assert "Детальные поисковые трассы" in ADMIN_JS
    assert "/api/admin/missions/trace/recent-attempts?hours=168&limit=100" in ADMIN_JS
    assert "Открыть timeline" in ADMIN_JS
    assert "Скачать JSONL трассу" in ADMIN_JS
    assert "query_text" in ADMIN_JS
    assert "query_variants" in ADMIN_JS


def test_admin_trace_timeline_opens_inline_and_scrolls_to_selected_attempt() -> None:
    assert "hunter-trace-inline" in ADMIN_JS
    assert "node.append(button, inlineTimeline)" in ADMIN_JS
    assert "showTimeline(item.mission_id, item.attempt_id, inlineTimeline, button)" in ADMIN_JS
    assert "host.scrollIntoView" in ADMIN_JS
    assert "button.textContent = 'Закрыть timeline'" in ADMIN_JS
    assert "button.textContent = 'Повторить открытие'" in ADMIN_JS
    assert "timelineBox" not in ADMIN_JS


def test_admin_trace_ui_does_not_render_sensitive_transport_fields() -> None:
    lowered = ADMIN_JS.lower()
    for forbidden in ("authorization", "api_key", "password", "cookie", "raw_payload"):
        assert forbidden not in lowered
