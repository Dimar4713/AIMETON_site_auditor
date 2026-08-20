from pathlib import Path


def test_acceptance_waits_for_real_terminal_state() -> None:
    text = Path(".github/workflows/accept-routerai-synthesis-stage.yml").read_text(encoding="utf-8")

    assert "deadline = mission_started + 360.0" in text
    assert "if status.get('state') in {'failed', 'completed'}:" in text
    polling_block = text.split("while time.monotonic() < deadline:", 1)[1].split(
        "assert status is not None", 1
    )[0]
    assert "'degraded'" not in polling_block
    assert "'blocked'" not in polling_block
