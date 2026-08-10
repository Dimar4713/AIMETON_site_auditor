from pathlib import Path


WORKFLOW = Path('.github/workflows/accept-service-catalog-stage.yml').read_text(encoding='utf-8')


def test_stage_acceptance_requires_sales_package_clipboard_contract() -> None:
    required = (
        'function companySalesPackageMarkdown(data)',
        'function appendSalesPackageCopyAction(output, data, status)',
        "button.textContent = 'Скопировать sales-пакет'",
        'navigator.clipboard.writeText(packageText)',
        'Первое сообщение — черновик — не отправлено',
        'Никакое сообщение не отправлено и никакое внешнее действие не выполнено.',
        'Не удалось скопировать sales-пакет:',
    )
    for token in required:
        assert token in WORKFLOW


def test_stage_acceptance_proves_clipboard_handler_is_local_only() -> None:
    assert "clipboard_body = catalog.split(" in WORKFLOW
    assert "clipboard export does not use local clipboard API" in WORKFLOW
    assert "for forbidden_call in ('fetch(', 'postJson(', 'requestSubmit(', '.submit(', 'sendEmail', 'sendMessage'):" in WORKFLOW
    assert 'clipboard export performs forbidden external action' in WORKFLOW


def test_stage_acceptance_reports_clipboard_safety_evidence() -> None:
    assert 'local sales-package clipboard export with draft/review labels: ✅' in WORKFLOW
    assert 'clipboard export performs no network/submit/outreach: ✅' in WORKFLOW
