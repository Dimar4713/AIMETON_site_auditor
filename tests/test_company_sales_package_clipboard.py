from pathlib import Path


CATALOG = Path("static/service-catalog.js").read_text(encoding="utf-8")


def _function_body(name: str, next_name: str) -> str:
    return CATALOG.split(f"function {name}", 1)[1].split(f"function {next_name}", 1)[0]


def _clipboard_action_body() -> str:
    return CATALOG.split(
        "function appendSalesPackageCopyAction(output, data, status) {", 1
    )[1].split("const companyForm = document.querySelector('#companyIntelligenceForm');", 1)[0]


def test_sales_package_copy_action_exists_only_after_company_result() -> None:
    assert "function appendSalesPackageCopyAction(output, data, status)" in CATALOG
    assert "button.textContent = 'Скопировать sales-пакет'" in CATALOG
    submit = CATALOG.split("companyForm?.addEventListener('submit'", 1)[1].split("const huntForm", 1)[0]
    render_pos = submit.index("renderCompanySalesHandoff(list, data);")
    copy_pos = submit.index("appendSalesPackageCopyAction(output, data, status);")
    assert render_pos < copy_pos
    assert "output.querySelector('.company-sales-package-copy')?.remove();" in submit


def test_export_keeps_facts_hypotheses_draft_and_readiness_separate() -> None:
    export = _function_body("companySalesPackageMarkdown(data) {", "appendSalesPackageCopyAction")
    required = (
        "## Подтверждённые / структурированные факты",
        "## Коммерческая возможность — гипотеза, не подтверждённый факт",
        "## Рабочие гипотезы и действия",
        "ЛПР — гипотеза:",
        "Причина контакта — гипотеза:",
        "Демо-сценарий — рабочая гипотеза:",
        "### Первое сообщение — черновик — не отправлено",
        "Следующий шаг — предлагаемое действие:",
        "## Готовность и ограничения",
        "Предварительный результат: требуется проверка перед внешним использованием.",
        "Блокеры выпуска:",
        "Никакое сообщение не отправлено и никакое внешнее действие не выполнено.",
    )
    for token in required:
        assert token in export


def test_export_preserves_hunter_lead_fit_context() -> None:
    export = _function_body("companySalesPackageMarkdown(data) {", "appendSalesPackageCopyAction")
    assert "form?.dataset.hunterLeadFit" in export
    assert "form?.dataset.hunterLeadFitReason" in export
    assert "Hunter lead-fit:" in export
    assert "Основание lead-fit:" in export


def test_clipboard_action_has_no_network_submit_or_outreach() -> None:
    copy = _clipboard_action_body()
    assert "navigator.clipboard.writeText(packageText)" in copy
    for forbidden in ("fetch(", "postJson(", "requestSubmit(", ".submit(", "sendEmail", "sendMessage"):
        assert forbidden not in copy


def test_clipboard_failure_is_visible_to_operator() -> None:
    copy = _clipboard_action_body()
    assert "буфер обмена недоступен в этом браузере" in copy
    assert "Не удалось скопировать sales-пакет:" in copy
    assert "Sales-пакет скопирован. Проверьте текст перед внешним использованием." in copy
