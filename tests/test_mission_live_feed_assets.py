from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_mission_detail_exposes_live_feed_region() -> None:
    html = (ROOT / "static" / "mission-detail.html").read_text(encoding="utf-8")

    assert 'id="mission-live-feed"' in html
    assert 'aria-live="polite"' in html
    assert 'id="mission-live-next"' in html
    assert 'id="mission-live-updated"' in html


def test_live_feed_uses_only_sanitized_records_projection() -> None:
    script = (ROOT / "static" / "mission-detail.js").read_text(encoding="utf-8")

    assert "/records`" in script
    assert "renderLiveFeed(mission, records)" in script
    assert "reason_code" in script
    assert "next_action" in script
    assert "input_snapshot" not in script
    assert "technical_snapshot" not in script
    assert "chain-of-thought" not in script
