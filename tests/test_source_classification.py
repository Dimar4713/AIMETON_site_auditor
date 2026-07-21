from app.external_sources import (
    classification_state,
    classify_result,
    classify_source_domain,
)


def test_query_intent_does_not_override_news_domain():
    source_class = classify_source_domain(
        "https://www.kommersant.ru/doc/123",
        official_host=None,
    )
    assert source_class == "news"
    assert classify_result("Компания открыла вакансии", "Ищет инженеров") == "jobs"
    assert classification_state(source_class, "jobs") == "ambiguous"


def test_vacancy_domain_is_workforce_even_for_finance_query():
    assert classify_source_domain("https://hh.ru/vacancy/123", None) == "workforce"
    assert classify_result("Вакансия аналитика", "Работа в компании") == "jobs"
    assert classification_state("workforce", "jobs") == "ambiguous"


def test_court_domain_and_document_agree():
    assert classify_source_domain("https://sudact.ru/arbitral/doc/123", None) == "court"
    assert classify_result("Решение суда", "Иск удовлетворен") == "court"
    assert classification_state("court", "court") == "classified"


def test_official_host_is_classified_independently():
    assert (
        classify_source_domain(
            "https://company.example/about",
            official_host="company.example",
        )
        == "official"
    )
    assert classify_result("О компании", "Продукция и услуги") == "unknown"
    assert classification_state("official", "unknown") == "classified"


def test_aggregator_keeps_result_kind_separate():
    assert classify_source_domain("https://sbis.ru/contragents/123", None) == "aggregator"
    assert classify_result("ООО Пример — ИНН и ОГРН", "Регистрационные данные") == "registry"
    assert classification_state("aggregator", "registry") == "classified"


def test_unknown_source_and_result_are_explicit():
    assert classify_source_domain("https://unmapped.example/page", None) == "unknown"
    assert classify_result("Страница", "Описание") == "unknown"
    assert classification_state("unknown", "unknown") == "unknown"
