from app.mission_bounded_runtime import _high_value_kind, _select_diverse_targets


def test_high_value_kind_recognizes_business_evidence_sections() -> None:
    assert _high_value_kind("https://clinic.example/doctors") == "workforce"
    assert _high_value_kind("https://clinic.example/team/ivanov") == "workforce"
    assert _high_value_kind("https://clinic.example/articles/implant-care") == "editorial"
    assert _high_value_kind("https://clinic.example/news/2026") == "editorial"
    assert _high_value_kind("https://clinic.example/documents/licenses") == "documents"
    assert _high_value_kind("https://clinic.example/prices") == "prices"
    assert _high_value_kind("https://clinic.example/services/caries") is None


def test_diverse_target_selection_prevents_services_from_monopolizing_budget() -> None:
    urls = [
        "https://clinic.example/services/caries",
        "https://clinic.example/services/hygiene",
        "https://clinic.example/doctors",
        "https://clinic.example/doctors/ivanov",
        "https://clinic.example/doctors/petrova",
        "https://clinic.example/articles/one",
        "https://clinic.example/articles/two",
        "https://clinic.example/articles/three",
        "https://clinic.example/documents",
        "https://clinic.example/prices",
    ]
    selected = _select_diverse_targets(urls)

    assert "https://clinic.example/services/caries" not in selected
    assert "https://clinic.example/services/hygiene" not in selected
    assert selected == [
        "https://clinic.example/doctors",
        "https://clinic.example/doctors/ivanov",
        "https://clinic.example/articles/one",
        "https://clinic.example/articles/three",
        "https://clinic.example/documents",
        "https://clinic.example/prices",
    ]


def test_diverse_target_selection_respects_existing_pages() -> None:
    selected = _select_diverse_targets(
        [
            "https://clinic.example/doctors",
            "https://clinic.example/articles/one",
            "https://clinic.example/documents",
            "https://clinic.example/prices",
        ],
        excluded={"https://clinic.example/doctors"},
    )
    assert "https://clinic.example/doctors" not in selected
    assert set(selected) == {
        "https://clinic.example/articles/one",
        "https://clinic.example/documents",
        "https://clinic.example/prices",
    }
