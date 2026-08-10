from app.hunter_lead_fit import classify_lead_fit, lead_fit_rank
from app.models import CompanyFact, SiteAnalysis


def _analysis(*, company_name: str = "Клиника", business_summary: str = "", legal_name: str | None = None) -> SiteAnalysis:
    facts = []
    if legal_name:
        facts.append(CompanyFact(field="legal_name", value=legal_name, confidence="Высокая"))
    return SiteAnalysis.model_construct(
        url="https://example.ru/",
        company_name=company_name,
        business_summary=business_summary,
        evidence=[],
        sources=[],
        company_facts=facts,
        business_machine_4x4=[],
        economic_signals=[],
        commercial_opportunity=None,
        agents=[],
        action_package=None,
        risks_and_assumptions=[],
    )


def test_explicit_private_dentistry_is_commercial() -> None:
    assessment = classify_lead_fit(
        title="Частная стоматология в Красноярске Al'denta",
        snippet="Лечение и имплантация зубов",
        url="https://aldenta.ru/",
        source_role="direct_candidate",
    )
    assert assessment.fit == "commercial_candidate"
    assert any(item.startswith("private_phrase:") for item in assessment.evidence)


def test_gosuslugi_direct_site_is_institutional() -> None:
    assessment = classify_lead_fit(
        title='КГБУЗ "КГСП №4"',
        snippet="Официальный сайт стоматологической поликлиники",
        url="https://kgsp4-r24.gosuslugi.ru/",
        source_role="direct_candidate",
    )
    assert assessment.fit == "institutional_candidate"
    assert assessment.evidence == ("institutional_host:gosuslugi.ru",)


def test_city_dental_polyclinic_is_institutional_without_gosuslugi_host() -> None:
    assessment = classify_lead_fit(
        title="Городская стоматологическая поликлиника № 7",
        snippet="Красноярск",
        url="https://kgsp7.ru/",
        source_role="direct_candidate",
    )
    assert assessment.fit == "institutional_candidate"


def test_university_dental_center_is_institutional() -> None:
    assessment = classify_lead_fit(
        title="Университетский центр стоматологии",
        snippet="Клиническая база университета",
        url="https://health.krasgmu.ru/universitetskij-centr-stomatologii",
        source_role="direct_candidate",
    )
    assert assessment.fit == "institutional_candidate"


def test_generic_branded_clinic_stays_unknown() -> None:
    assessment = classify_lead_fit(
        title="Стоматология в Красноярске — Центр стоматологии Сапфир",
        snippet="Имплантация, лечение, цены и запись",
        url="https://sapfircs.ru/",
        source_role="direct_candidate",
    )
    assert assessment.fit == "unknown_candidate"


def test_generic_clinic_word_is_not_private_proof() -> None:
    assessment = classify_lead_fit(
        title="Стоматологическая клиника Красноярск",
        snippet="Запись на прием и цены",
        url="https://example-dent.ru/",
        source_role="direct_candidate",
    )
    assert assessment.fit == "unknown_candidate"


def test_rzd_medicine_is_not_guessed_institutional_from_brand_alone() -> None:
    assessment = classify_lead_fit(
        title="РЖД-Медицина — ортопедическая стоматология",
        snippet="Услуги и цены в Красноярске",
        url="https://krasnoyarsk.rzd-medicine.ru/services/stomatologiya",
        source_role="direct_candidate",
    )
    assert assessment.fit == "unknown_candidate"


def test_deep_legal_name_can_confirm_commercial_form() -> None:
    assessment = classify_lead_fit(
        title="Стоматология МедиДент",
        snippet="Красноярск",
        url="https://medident.ru/",
        source_role="direct_candidate",
        analysis=_analysis(legal_name='ООО "МедиДент"'),
    )
    assert assessment.fit == "commercial_candidate"
    assert any(item == "legal_form:ооо" for item in assessment.evidence)


def test_supporting_source_has_no_lead_fit() -> None:
    assessment = classify_lead_fit(
        title="Рейтинг стоматологий Красноярска",
        snippet="400 клиник",
        url="https://32top.ru/krasnoyarsk/stomatologii",
        source_role="supporting_source",
    )
    assert assessment.fit == "not_applicable"


def test_lead_fit_rank_is_commercial_unknown_institutional() -> None:
    assert lead_fit_rank("commercial_candidate") > lead_fit_rank("unknown_candidate")
    assert lead_fit_rank("unknown_candidate") > lead_fit_rank("institutional_candidate")
