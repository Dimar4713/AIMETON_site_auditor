from app.hunter_source_role import classify_source_role, is_supporting_host


def test_real_company_sites_remain_direct_candidates() -> None:
    for title, url in (
        ("Стоматология в Красноярске", "https://sapfircs.ru/"),
        ("Стоматология San-Dent в Красноярске", "https://san-dent-clinic.ru/"),
        ("Эстетическая стоматология в Красноярске", "https://allure-dent.ru/esteticheskaya-stomatologiya"),
        ("Ортодонтическая клиника Одус в Красноярске", "https://odus.info/"),
    ):
        assert classify_source_role(title, "лечение зубов и запись", url) == "direct_candidate"


def test_real_e2e_directories_and_articles_are_supporting_sources() -> None:
    cases = (
        ("Лучшие стоматологии в Красноярске", "https://dentistfind.ru/krasnoyarsk"),
        ("Лучшие стоматологии в Красноярске 2026: рейтинг", "https://www.kp.ru/russia/krasnoyarsk/lechenie/luchshie-stomatologii/"),
        ("Стоматология рядом со мной на карте", "https://zoon.ru/krasnoyarsk/medical/type/stomatologicheskaya_klinika/"),
        ("ТОП-50: Лечение зубов в Красноярске", "https://krasnoyarsk.jsprav.ru/lechenie-zubov/"),
        ("Стоматологии в Красноярске", "https://dent-list.ru/krasnoyarsk"),
        ("Где лечить зубы в Красноярске", "https://vc.ru/top_rating/2997674-gde-lechit-zuby-v-krasnoyarske"),
        ("392 лучших стоматологий в Красноярске", "https://alldantist.ru/krasnoyarsk"),
    )
    for title, url in cases:
        assert classify_source_role(title, "адреса, цены, отзывы", url) == "supporting_source"


def test_subdomains_of_known_sources_are_supporting() -> None:
    assert is_supporting_host("krsk.infodoctor.ru")
    assert is_supporting_host("krasnoyarsk.yp.ru")
    assert is_supporting_host("krsk.docdoc.ru")


def test_challenge_pages_are_not_direct_candidates() -> None:
    assert classify_source_role(
        "Ограничение доступа",
        "",
        "https://example-clinic.ru/",
    ) == "blocked_source"
