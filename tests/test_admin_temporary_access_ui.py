from pathlib import Path


STATIC = Path("static")


def test_admin_workspace_exposes_temporary_access_issuer():
    html = (STATIC / "admin-workspace.html").read_text(encoding="utf-8")
    assert 'id="temporary-access-form"' in html
    assert 'id="temporary-access-user-id"' in html
    assert 'id="temporary-access-ttl"' in html
    assert 'id="temporary-access-max-uses"' in html
    assert 'id="temporary-access-issued-link"' in html
    assert 'id="temporary-access-copy"' in html
    assert '/static/admin-temporary-access.js' in html
    assert 'Выдать временную ссылку' in html


def test_admin_temporary_access_ui_uses_secure_api_and_does_not_persist_secret():
    script = (STATIC / "admin-temporary-access.js").read_text(encoding="utf-8")
    assert "'/api/auth/admin/temporary-access-tokens'" in script
    assert "X-CSRF-Token" in script
    assert "magic_link_fragment" in script
    assert "navigator.clipboard.writeText" in script
    assert "localStorage" not in script
    assert "sessionStorage" not in script
    assert "issuedLink.value = ''" in script
    assert "Отозвать доступ" in script


def test_admin_link_is_fragment_based_not_query_based():
    script = (STATIC / "admin-temporary-access.js").read_text(encoding="utf-8")
    assert "issued.magic_link_fragment" in script
    assert "?access_token=" not in script
    assert "?token=" not in script
