from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import accb_routerai_live_entrypoint as entrypoint
import accb_routerai_live_pilot as pilot


def test_transport_selection_prefers_chat_for_comparable_models() -> None:
    assert entrypoint._transport_for_apis(["responses", "chat"]) == "chat"
    assert entrypoint._transport_for_apis(["responses"]) == "responses"
    assert entrypoint._transport_for_apis(["messages"]) is None


def test_responses_input_keeps_system_as_instructions() -> None:
    instructions, inputs = entrypoint._responses_input(
        [
            {"role": "system", "content": "system contract"},
            {"role": "user", "content": "task"},
        ]
    )
    assert instructions == "system contract"
    assert inputs == [{"role": "user", "content": "task"}]


def test_responses_transport_normalizes_text_usage_and_provider_pin(monkeypatch) -> None:
    captured = {}

    def fake_http_json(url, *, payload=None, api_key=None, timeout=180):
        captured["url"] = url
        captured["payload"] = payload
        captured["api_key"] = api_key
        captured["timeout"] = timeout
        return (
            200,
            {
                "id": "resp_test",
                "model": "openai/gpt-5.6-sol",
                "provider": "OpenAI",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "OK"}],
                    }
                ],
                "usage": {"input_tokens": 123, "output_tokens": 4, "total_tokens": 127},
            },
            0.25,
        )

    monkeypatch.setattr(pilot, "http_json", fake_http_json)
    endpoint = {
        "api_transport": "responses",
        "tag": "openai",
        "supported_parameters": ["max_tokens"],
    }
    body, elapsed = entrypoint.adaptive_chat(
        "secret",
        "openai/gpt-5.6-sol",
        endpoint,
        [
            {"role": "system", "content": "system contract"},
            {"role": "user", "content": "task"},
        ],
        max_tokens=4,
        temperature=0.0,
        timeout=120,
    )

    assert captured["url"] == f"{pilot.BASE_URL}/responses"
    assert captured["payload"]["model"] == "openai/gpt-5.6-sol"
    assert captured["payload"]["instructions"] == "system contract"
    assert captured["payload"]["input"] == [{"role": "user", "content": "task"}]
    assert captured["payload"]["provider"] == {
        "only": ["openai"],
        "allow_fallbacks": False,
    }
    assert "temperature" not in captured["payload"]
    assert pilot.response_text(body) == "OK"
    assert pilot.usage(body) == (123, 4, 127)
    assert body["_routerai_transport"] == "responses"
    assert elapsed == 0.25
