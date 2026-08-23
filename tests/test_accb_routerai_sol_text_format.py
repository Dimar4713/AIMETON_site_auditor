from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import accb_routerai_live_pilot as pilot
import accb_routerai_retry_entrypoint as retry


def _endpoint() -> dict:
    return {
        "api_transport": "responses",
        "tag": "openai",
        "supported_parameters": [
            "reasoning",
            "include_reasoning",
            "response_format",
        ],
    }


def test_sol_live_responses_translates_chat_controls_to_native_contract(monkeypatch) -> None:
    calls: list[dict] = []

    def fake_http_json(*args, **kwargs):
        calls.append(kwargs["payload"])
        return 200, {
            "error": None,
            "id": "resp_live",
            "model": retry.SOL_MODEL,
            "provider": "openai",
            "usage": {"input_tokens": 1000, "output_tokens": 10, "total_tokens": 1010},
            "output": [],
        }, 0.25

    monkeypatch.setattr(pilot, "http_json", fake_http_json)
    monkeypatch.setattr(pilot, "estimated_cost", lambda endpoint, prompt, completion: 1.25)

    body, elapsed = retry._sol_chat(
        "secret",
        retry.SOL_MODEL,
        _endpoint(),
        [{"role": "user", "content": "live"}],
        max_tokens=8192,
        timeout=30,
    )

    assert elapsed == 0.25
    assert retry._sol_usage(body) == (1000, 10, 1010)
    assert len(calls) == 1
    payload = calls[0]
    assert payload["max_output_tokens"] == 8192
    assert "max_tokens" not in payload
    assert "response_format" not in payload
    assert payload["text"] == {"format": {"type": "json_object"}}
    assert payload["reasoning"] == {"effort": "low"}
    assert "include_reasoning" not in payload
    assert payload["provider"] == {"only": ["openai"], "allow_fallbacks": False}


def test_sol_probe_keeps_generation_controls_off(monkeypatch) -> None:
    calls: list[dict] = []

    def fake_http_json(*args, **kwargs):
        calls.append(kwargs["payload"])
        return 200, {
            "error": None,
            "id": "resp_probe",
            "usage": {"input_tokens": 475, "output_tokens": 5, "total_tokens": 480},
            "output": [],
        }, 0.1

    monkeypatch.setattr(pilot, "http_json", fake_http_json)

    body, _ = retry._sol_chat(
        "secret",
        retry.SOL_MODEL,
        _endpoint(),
        [{"role": "user", "content": "probe"}],
        max_tokens=4,
        timeout=30,
    )

    assert retry._sol_usage(body) == (475, 5, 480)
    payload = calls[0]
    assert payload["max_output_tokens"] == 4
    assert "max_tokens" not in payload
    assert "response_format" not in payload
    assert "text" not in payload
    assert "reasoning" not in payload
    assert "include_reasoning" not in payload
    assert payload["provider"] == {"only": ["openai"], "allow_fallbacks": False}
