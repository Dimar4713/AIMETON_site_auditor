from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


STATIC = Path("static")


def test_root_contains_login_gate_and_hidden_workspace():
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert 'id="authGate"' in html
    assert 'id="loginForm"' in html
    assert 'id="loginUsername"' in html
    assert 'id="loginPassword"' in html
    assert 'id="workspace" hidden' in html
    assert 'id="userIdentity"' in html
    assert 'id="logoutBtn"' in html
    assert '/static/auth-ui.js' in html
    assert '/static/auth-ui.css' in html


def test_auth_ui_uses_server_session_without_browser_secret_storage():
    script = (STATIC / "auth-ui.js").read_text(encoding="utf-8")
    assert "'/api/auth/me'" in script
    assert "'/api/auth/login'" in script
    assert "'/api/auth/logout'" in script
    assert "credentials: 'same-origin'" in script
    assert "localStorage" not in script
    assert "sessionStorage" not in script
    assert "elements.password.value = ''" in script
    assert "token" not in script.casefold()


def test_auth_ui_exposes_typed_user_states():
    script = (STATIC / "auth-ui.js").read_text(encoding="utf-8")
    for phase in ("loading", "anonymous", "authenticated"):
        assert phase in script
    assert "Неверное имя пользователя или пароль" in script
    assert "Сервис авторизации временно недоступен" in script
    assert "Нет связи с сервером" in script
    assert "Сессия завершена" in script


def test_login_form_does_not_place_credentials_in_url():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert '<form id="loginForm"' in html
    assert 'method="get"' not in html.casefold()
    assert 'type="password"' in html
    assert 'autocomplete="current-password"' in html


def test_workspace_identity_distinguishes_admin_and_user_without_secrets():
    script = (STATIC / "auth-ui.js").read_text(encoding="utf-8")
    assert "role === 'admin'" in script
    assert "Администратор" in script
    assert "Пользователь" in script
    forbidden = ("password_hash", "session_token", "bootstrap_admin_password")
    for value in forbidden:
        assert value not in script.casefold()
