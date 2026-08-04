from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "static" / "live-analysis.js"


def test_live_analysis_reports_active_connection_during_quiet_phases() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert "Связь с миссией активна" in script
    assert "Система работает, ожидаем завершение текущей подзадачи" in script
    assert "Длительная операция продолжается, новых этапов пока нет" in script
    assert "Последний сигнал" in script
    assert "Проверка сервера выполняется каждые 1,2 сек" in script
    assert "mission-heartbeat__dot" in script
    assert "setInterval(refreshClockAndHeartbeat, 1000)" in script


def test_live_analysis_heartbeat_does_not_expose_internal_payloads() -> None:
    script = SCRIPT.read_text(encoding="utf-8").lower()

    for forbidden in (
        "chain-of-thought",
        "raw_prompt",
        "provider_payload",
        "access_token",
        "secret_key",
    ):
        assert forbidden not in script
