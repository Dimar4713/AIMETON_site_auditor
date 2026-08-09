from app import discovery
from app.models import HuntRequest


def _request(industry: str = "стоматология") -> HuntRequest:
    return HuntRequest(region="Красноярск", industries=[industry])


def test_requested_industry_directly_boosts_relevant_candidate() -> None:
    result = discovery._pre_score(
        _request(),
        "Частная стоматология Альдента в Красноярске",
        "Лечение зубов, имплантация, ортодонтия",
        "https://aldenta.ru/",
    )

    assert result.status == "calculated"
    assert result.factors["industry_match"] == 25
    assert "обнаружено прямое соответствие заданной отрасли" in result.reasons
    assert result.score is not None and result.score >= 75


def test_morphological_industry_form_is_detected_by_bounded_stem() -> None:
    result = discovery._pre_score(
        _request(),
        "Стоматологическая клиника Красноярск",
        "Имплантация и лечение зубов",
        "https://clinic.ru/",
    )

    assert result.factors["industry_match"] == 25


def test_strong_dentistry_service_terms_match_without_umbrella_word() -> None:
    result = discovery._pre_score(
        _request(),
        "Allure Dent — имплантация зубов в Красноярске",
        "Протезирование и восстановление зубов",
        "https://allure-dent.ru/implantaciya",
    )

    assert result.factors["industry_match"] == 25


def test_dentistry_translit_url_and_orthodontics_match() -> None:
    result = discovery._pre_score(
        _request(),
        "Исправление прикуса в Красноярске",
        "Брекеты и консультация ортодонта",
        "https://example-dent.ru/ortodontiya",
    )

    assert result.factors["industry_match"] == 25


def test_generic_medical_clinic_does_not_get_dentistry_match() -> None:
    result = discovery._pre_score(
        _request(),
        "Многопрофильный медицинский центр в Красноярске",
        "Диагностика, терапия, хирургия",
        "https://medical-center.ru/",
    )

    assert result.factors["industry_match"] == 0


def test_generic_clinic_request_does_not_inherit_dentistry_strong_markers() -> None:
    result = discovery._pre_score(
        _request("клиника"),
        "Многопрофильный медицинский центр в Красноярске",
        "Диагностика, терапия, хирургия",
        "https://medical-center.ru/",
    )

    assert "имплант" not in discovery._industry_markers(_request("клиника"))
    assert result.factors["industry_match"] == 0


def test_industry_factor_stays_explicit_for_insufficient_data() -> None:
    result = discovery._pre_score(
        _request(),
        "",
        "",
        "https://example.ru/",
    )

    assert result.status == "insufficient_data"
    assert result.factors["industry_match"] is None
