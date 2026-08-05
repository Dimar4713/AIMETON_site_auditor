from pathlib import Path


def test_instant_umel_reporter_loads_before_live_analysis_owner() -> None:
    html = Path("static/index.html").read_text(encoding="utf-8")
    instant = html.index("/static/instant-umel-reporter.js")
    owner = html.index("/static/live-analysis.js")
    assert instant < owner


def test_instant_umel_reporter_is_canonical_and_non_blocking() -> None:
    script = Path("static/instant-umel-reporter.js").read_text(encoding="utf-8")
    assert "mission.received" in script
    assert "🧭" in script
    assert "performance.now()" in script
    assert "stopImmediatePropagation" not in script
    assert "preventDefault" not in script
    assert "aria-live=\"assertive\"" in script
