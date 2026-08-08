from types import SimpleNamespace

from app.external_verification import document_matches_entity


def _anchors():
    return SimpleNamespace(
        domain="example.org",
        inn=None,
        ogrn=None,
        cities=("Красноярск",),
        phones=(),
    )


def test_document_identity_accepts_official_domain() -> None:
    matched, reason = document_matches_entity(
        "Официальная страница компании с подтвержденными сведениями.",
        company_name="Тестовая компания",
        anchors=_anchors(),
        document_url="https://example.org/about",
    )
    assert matched is True
    assert reason == "official_domain_match"


def test_document_identity_accepts_name_and_region() -> None:
    matched, reason = document_matches_entity(
        "Тестовая компания работает в Красноярске. Контакты и описание.",
        company_name="Тестовая компания",
        anchors=_anchors(),
        document_url="https://catalog.example/item",
    )
    assert matched is True
    assert reason == "name_and_region_match"


def test_document_identity_rejects_same_name_from_other_region() -> None:
    matched, reason = document_matches_entity(
        "Тестовая компания работает в Перми. Это другая организация.",
        company_name="Тестовая компания",
        anchors=_anchors(),
        document_url="https://catalog.example/perm",
    )
    assert matched is False
    assert reason == "identity_not_confirmed"
