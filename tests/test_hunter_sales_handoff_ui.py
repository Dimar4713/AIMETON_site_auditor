from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = (ROOT / "static" / "service-catalog.js").read_text(encoding="utf-8")
CONTEXT = (ROOT / "static" / "hunter-company-handoff-context.js").read_text(encoding="utf-8")


def test_hunter_cards_expose_commercial_lead_fit_separately_from_source_role() -> None:
    assert "function leadFitPresentation(candidate)" in CATALOG
    assert "Коммерческий кандидат" in CATALOG
    assert "Коммерческий статус не подтверждён" in CATALOG
    assert "Институциональная организация" in CATALOG
    assert "candidate.lead_fit_reason" in CATALOG
    assert "Основание коммерческого статуса" in CATALOG
    assert "const classification = classifyCandidate(candidate);" in CATALOG
    assert "const leadFit = leadFitPresentation(candidate);" in CATALOG


def test_hunter_handoff_preserves_lead_fit_without_auto_research() -> None:
    assert "form.dataset.hunterLeadFit = String(candidate.lead_fit || '')" in CATALOG
    assert "form.dataset.hunterLeadFitReason = String(candidate.lead_fit_reason || '')" in CATALOG
    assert "Hunter: ${LEAD_FIT_LABELS[leadFit]}" in CONTEXT
    assert "Основание приоритета: ${leadFitReason}" in CONTEXT

    handoff_body = CATALOG.split(
        "function handoffCandidate(candidate, fallbackRegion)", 1
    )[1].split("function appendCandidate", 1)[0]
    assert "postJson(" not in handoff_body
    assert "requestSubmit(" not in handoff_body
    assert ".submit(" not in handoff_body


def test_company_intelligence_surfaces_structured_facts_with_confidence() -> None:
    assert "const COMPANY_FACT_LABELS" in CATALOG
    for field in ("legal_name", "phones", "emails", "website", "executives"):
        assert f"{field}:" in CATALOG
    assert "Факт · ${COMPANY_FACT_LABELS[fact.field]}" in CATALOG
    assert "Уверенность: ${fact.confidence || 'не указана'}" in CATALOG
    assert "fact.source_ids" in CATALOG


def test_sales_package_labels_hypotheses_and_never_claims_message_was_sent() -> None:
    assert "Коммерческая возможность — гипотеза" in CATALOG
    assert "Не является подтверждённым фактом" in CATALOG
    assert "ЛПР — гипотеза" in CATALOG
    assert "Требует проверки по первичным источникам" in CATALOG
    assert "Причина контакта — гипотеза" in CATALOG
    assert "Демо-сценарий — рабочая гипотеза" in CATALOG
    assert "Первое сообщение — черновик, не отправлено" in CATALOG
    assert "Автоматическая отправка отключена; решение остаётся за человеком" in CATALOG
    assert "Следующий шаг — предлагаемое действие" in CATALOG
    assert "Выполняется только после явного решения человека" in CATALOG


def test_preliminary_readiness_is_visible_before_external_use() -> None:
    assert "analysis.readiness || null" in CATALOG
    assert "readiness.client_release_eligible === false" in CATALOG
    assert "Предварительный результат: требуется проверка перед внешним использованием." in CATALOG
    assert "Блокеры выпуска" in CATALOG


def test_company_intelligence_uses_existing_endpoint_only_after_explicit_submit() -> None:
    submit_block = CATALOG.split(
        "companyForm?.addEventListener('submit'", 1
    )[1].split("const huntForm", 1)[0]
    assert "postJson('/api/company-intelligence', payload)" in submit_block
    assert "renderCompanySalesHandoff(list, data);" in submit_block
    assert "sendEmail" not in CATALOG
    assert "sendMessage" not in CATALOG
