from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "static"


def test_human_report_hides_machine_artifacts_from_primary_view() -> None:
    script = (STATIC / "human-report.js").read_text(encoding="utf-8")
    guard = (STATIC / "analyze-response-guard.js").read_text(encoding="utf-8")

    assert "Насколько можно доверять результату" in script
    assert "Что ещё требуется проверить" in script
    assert "Юридическое название" in script
    assert "Технические сведения для эксперта" in script
    assert "human-report.js" in guard


def test_human_report_preserves_machine_details_for_experts() -> None:
    script = (STATIC / "human-report.js").read_text(encoding="utf-8")

    for code in (
        "schema_validated",
        "identity_unresolved",
        "mandatory_verticals_incomplete",
        "human_review_and_signed_report_required",
    ):
        assert code in script

    assert "technical-details" in script
    assert "@media(max-width:640px)" in script
