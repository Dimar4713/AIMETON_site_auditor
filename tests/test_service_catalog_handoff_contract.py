from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
CATALOG = (ROOT / "static" / "service-catalog.js").read_text(encoding="utf-8")


def test_hunter_and_company_intelligence_surfaces_exist():
    required_ids = (
        'id="hunterForm"',
        'id="hunterOutput"',
        'id="companyIntelligenceForm"',
        'id="companyName"',
        'id="companyUrl"',
        'id="companyRegion"',
    )
    for marker in required_ids:
        assert marker in INDEX


def test_candidate_handoff_is_explicit_and_does_not_auto_submit():
    assert "function handoffCandidate(candidate, fallbackRegion)" in CATALOG
    assert "selectService('company-intelligence')" in CATALOG
    assert "document.querySelector('#companyName').value = name" in CATALOG
    assert "document.querySelector('#companyUrl').value = url" in CATALOG
    assert "document.querySelector('#companyRegion').value = region" in CATALOG
    assert "Проверьте их и явно запустите исследование" in CATALOG

    handoff_body = CATALOG.split(
        "function handoffCandidate(candidate, fallbackRegion)", 1
    )[1].split("function appendCandidate", 1)[0]
    assert ".submit(" not in handoff_body
    assert "requestSubmit(" not in handoff_body
    assert "postJson(" not in handoff_body


def test_candidate_card_is_actionable_and_truthful_when_name_only():
    assert "function appendCandidate(container, candidate, fallbackRegion)" in CATALOG
    assert "action.textContent = 'Исследовать компанию'" in CATALOG
    assert "action.addEventListener('click'" in CATALOG
    assert "Недостаточно данных: найдено только название компании." in CATALOG
    assert "nameOnly ? ' · Недостаточно данных'" in CATALOG


def test_handoff_accepts_only_http_urls():
    assert "function safeHttpUrl(value)" in CATALOG
    assert "['http:', 'https:'].includes(url.protocol)" in CATALOG
    assert "link.rel = 'noopener noreferrer'" in CATALOG
    assert "link.target = '_blank'" in CATALOG
