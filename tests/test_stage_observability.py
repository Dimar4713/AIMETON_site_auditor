from scripts.stage_observability import is_safe_mcp_redirect


STAGE_URL = "https://stage-auditor.aimeton.ru"


def test_accepts_direct_success():
    assert is_safe_mcp_redirect(STAGE_URL, {"status": 200})


def test_accepts_safe_relative_redirect():
    assert is_safe_mcp_redirect(STAGE_URL, {"status": 307, "location": "/mcp/"})


def test_accepts_safe_absolute_redirect():
    assert is_safe_mcp_redirect(
        STAGE_URL,
        {"status": 308, "location": "https://stage-auditor.aimeton.ru/mcp/"},
    )


def test_rejects_cross_origin_redirect():
    assert not is_safe_mcp_redirect(
        STAGE_URL,
        {"status": 307, "location": "https://attacker.example/mcp/"},
    )


def test_rejects_http_downgrade():
    assert not is_safe_mcp_redirect(
        STAGE_URL,
        {"status": 307, "location": "http://stage-auditor.aimeton.ru/mcp/"},
    )


def test_rejects_wrong_path_or_query():
    assert not is_safe_mcp_redirect(STAGE_URL, {"status": 307, "location": "/admin/"})
    assert not is_safe_mcp_redirect(STAGE_URL, {"status": 307, "location": "/mcp/?next=elsewhere"})


def test_rejects_missing_location_and_unexpected_status():
    assert not is_safe_mcp_redirect(STAGE_URL, {"status": 307})
    assert not is_safe_mcp_redirect(STAGE_URL, {"status": 302, "location": "/mcp/"})
