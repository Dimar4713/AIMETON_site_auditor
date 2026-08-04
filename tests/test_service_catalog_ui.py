from pathlib import Path


STATIC = Path(__file__).resolve().parents[1] / "static"


def test_service_catalog_exposes_three_real_services_and_honest_beta() -> None:
    index = (STATIC / "index.html").read_text(encoding="utf-8")
    script = (STATIC / "service-catalog.js").read_text(encoding="utf-8")

    for service in ("site-audit", "company-intelligence", "hunter", "interface-audit"):
        assert f'data-service-card="{service}"' in index

    assert 'data-service-card="interface-audit"' in index
    assert "disabled" in index
    assert "Beta" in index

    assert "/api/analyze/start" in (STATIC / "live-analysis.js").read_text(encoding="utf-8")
    assert "/api/company-intelligence" in script
    assert "/api/hunt" in script


def test_service_catalog_is_mobile_and_safe_by_construction() -> None:
    index = (STATIC / "index.html").read_text(encoding="utf-8")
    styles = (STATIC / "service-catalog.css").read_text(encoding="utf-8")
    script = (STATIC / "service-catalog.js").read_text(encoding="utf-8").lower()

    assert 'name="viewport"' in index
    assert "@media(max-width:720px)" in styles
    assert "credentials: 'same-origin'" in script
    assert "textcontent" in script

    for forbidden in ("chain-of-thought", "raw_prompt", "provider_payload", "access_token", "secret_key"):
        assert forbidden not in index.lower()
        assert forbidden not in script


def test_catalog_is_initial_experience_and_forms_open_only_after_selection() -> None:
    index = (STATIC / "index.html").read_text(encoding="utf-8")
    script = (STATIC / "service-catalog.js").read_text(encoding="utf-8")

    for service in ("site-audit", "company-intelligence", "hunter"):
        assert f'data-service-panel="{service}" hidden' in index

    for action in ("Проверить сайт →", "Исследовать компанию →", "Найти клиентов →"):
        assert action in index

    assert "clearSelection();" in script
    assert "selectService('site-audit')" not in script
    assert "panel.hidden = true" in script
