from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
SCRIPT = (ROOT / "static" / "hunter-company-handoff-context.js").read_text(encoding="utf-8")


def test_hunter_company_handoff_context_script_is_loaded() -> None:
    assert "/static/hunter-company-handoff-context.js" in INDEX
    assert INDEX.index("/static/service-catalog.js") < INDEX.index("/static/hunter-company-handoff-context.js")


def test_handoff_context_identifies_selected_object_by_domain() -> None:
    assert "Выбранный кандидат" in SCRIPT
    assert "Компания по сайту ${host}" in SCRIPT
    assert "Сайт: ${host}" in SCRIPT
    assert "Из поиска клиентов" in SCRIPT
    assert "Название из поисковой выдачи" in SCRIPT


def test_handoff_context_does_not_invent_or_auto_submit_company_identity() -> None:
    assert "requestSubmit(" not in SCRIPT
    assert ".submit(" not in SCRIPT
    assert "postJson(" not in SCRIPT
    assert "document.querySelector('#companyName').value =" not in SCRIPT


def test_company_intelligence_completion_status_names_selected_domain() -> None:
    assert "Профиль подготовлен для ${host}." in SCRIPT
    assert "safeHost(document.querySelector('#companyUrl')?.value)" in SCRIPT
