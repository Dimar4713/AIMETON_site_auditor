from pathlib import Path


WORKFLOW = Path('.github/workflows/accept-service-catalog-stage.yml').read_text(encoding='utf-8')


def test_stage_acceptance_requires_sales_handoff_contract() -> None:
    required = (
        'hunter-company-handoff-context.js',
        'function leadFitPresentation(candidate)',
        'Коммерческий кандидат',
        'Основание коммерческого статуса:',
        'form.dataset.hunterLeadFit',
        'form.dataset.hunterLeadFitReason',
        'function renderCompanySalesHandoff(container, data)',
        'Факт · ${COMPANY_FACT_LABELS[fact.field]}',
        'Коммерческая возможность — гипотеза',
        'ЛПР — гипотеза',
        'Первое сообщение — черновик, не отправлено',
        'Предварительный результат: требуется проверка перед внешним использованием.',
    )
    for token in required:
        assert token in WORKFLOW


def test_stage_acceptance_guards_handoff_from_automatic_actions() -> None:
    assert "handoff_body = catalog.split(" in WORKFLOW
    assert "for forbidden_call in ('postJson(', 'requestSubmit(', '.submit('):" in WORKFLOW
    assert 'handoff performs forbidden automatic action' in WORKFLOW
    assert 'explicit submit-only provider boundary' in WORKFLOW


def test_stage_acceptance_reports_fact_hypothesis_readiness_boundaries() -> None:
    assert 'factual identity/contact fields with confidence/source context: ✅' in WORKFLOW
    assert 'opportunity/LPR/contact/demo/message explicitly labelled as hypotheses or drafts: ✅' in WORKFLOW
    assert 'preliminary readiness/release blockers visible: ✅' in WORKFLOW
    assert 'handoff performs no automatic submit/outreach: ✅' in WORKFLOW
