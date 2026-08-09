from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_admin_workspace_exposes_dedicated_hunter_settings_panel() -> None:
    html = (ROOT / "static" / "admin-workspace.html").read_text(encoding="utf-8")
    script = (ROOT / "static" / "admin-hunter-settings.js").read_text(encoding="utf-8")

    assert 'id="hunter-settings-title">Настройки Hunter<' in html
    assert 'id="hunter-settings-form"' in html
    assert 'id="hunter-setting-max-queries"' in html
    assert 'id="hunter-setting-results-per-query"' in html
    assert 'id="hunter-setting-max-candidates"' in html
    assert 'id="hunter-setting-output-limit"' in html
    assert 'id="hunter-setting-minimum-pre-score"' in html
    assert 'id="hunter-setting-deep-audit-score"' in html
    assert 'id="hunter-setting-concurrency"' in html
    assert 'fallback_first_nonempty' in html
    assert 'Объединение выдач нескольких providers пока не реализовано' in html
    assert '/api/admin/hunter-settings' in script
    assert "'X-CSRF-Token': csrfToken()" in script


def test_user_hunter_form_no_longer_hardcodes_operational_limits() -> None:
    script = (ROOT / "static" / "service-catalog.js").read_text(encoding="utf-8")
    hunter_block = script.split("const huntForm =", 1)[1]

    assert "max_queries:" not in hunter_block
    assert "results_per_query:" not in hunter_block
    assert "max_candidates:" not in hunter_block
    assert "output_limit:" not in hunter_block
    assert "concurrency:" not in hunter_block
    assert "renderHunterCandidates(list, data.candidates || []" in hunter_block
