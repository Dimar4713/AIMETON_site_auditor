from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import accb_routerai_live_pilot as pilot
import accb_routerai_retry_entrypoint as retry


def test_retry_models_exclude_already_scored_models() -> None:
    assert retry.RETRY_MODELS == [
        "deepseek/deepseek-v4-pro-0813",
        "moonshotai/kimi-k3",
        "openai/gpt-5.6-sol",
    ]
    assert "z-ai/glm-5.2" not in retry.RETRY_MODELS
    assert "qwen/qwen3.7-plus" not in retry.RETRY_MODELS
    assert retry.RETRY_MAX_OUTPUT_TOKENS == 8192
    assert retry.RETRY_OF_RUN == 32586356270


def test_chat_retry_pins_provider_and_controls_reasoning(monkeypatch) -> None:
    captured = {}

    def fake_http_json(url, *, payload=None, api_key=None, timeout=180):
        captured["url"] = url
        captured["payload"] = payload
        return (
            200,
            {
                "model": "deepseek-v4-pro",
                "provider": "DeepSeek",
                "choices": [{"message": {"content": '{"scenario_id":"ACCB-DEV-001"}'}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
            },
            0.5,
        )

    monkeypatch.setattr(pilot, "http_json", fake_http_json)
    endpoint = {
        "api_transport": "chat",
        "tag": "deepseek",
        "supported_parameters": ["reasoning", "include_reasoning", "response_format", "temperature"],
    }
    body, elapsed = retry.retry_chat(
        "secret",
        "deepseek/deepseek-v4-pro-0813",
        endpoint,
        [{"role": "user", "content": "Return JSON"}],
        max_tokens=retry.RETRY_MAX_OUTPUT_TOKENS,
        temperature=0.0,
        timeout=120,
    )
    payload = captured["payload"]
    assert captured["url"] == f"{pilot.BASE_URL}/chat/completions"
    assert payload["provider"] == {"only": ["deepseek"], "allow_fallbacks": False}
    assert payload["reasoning"] == {"effort": "low"}
    assert payload["include_reasoning"] is False
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["temperature"] == 0.0
    assert body["choices"][0]["message"]["content"].startswith("{")
    assert body["_retry_visible_text_present"] is True
    assert elapsed == 0.5


def test_probe_disables_reasoning_and_does_not_require_visible_text(monkeypatch) -> None:
    captured = {}

    def fake_http_json(url, *, payload=None, api_key=None, timeout=180):
        captured["payload"] = payload
        return (
            200,
            {
                "choices": [{"message": {"content": "", "reasoning_content": "SENSITIVE_SENTINEL"}}],
                "usage": {"prompt_tokens": 321, "completion_tokens": 4, "total_tokens": 325},
            },
            0.2,
        )

    monkeypatch.setattr(pilot, "http_json", fake_http_json)
    endpoint = {
        "api_transport": "chat",
        "tag": "deepseek",
        "supported_parameters": ["reasoning", "include_reasoning", "response_format", "temperature"],
    }
    body, _ = retry.retry_chat(
        "secret",
        "deepseek/deepseek-v4-pro-0813",
        endpoint,
        [{"role": "user", "content": "probe"}],
        max_tokens=4,
        timeout=120,
    )
    payload = captured["payload"]
    assert "reasoning" not in payload
    assert "include_reasoning" not in payload
    assert "response_format" not in payload
    assert pilot.usage(body) == (321, 4, 325)
    assert body["_retry_visible_text_present"] is False
    assert "SENSITIVE_SENTINEL" not in str(body["_safe_response_shape"])


def test_responses_retry_accepts_nested_routerai_envelope(monkeypatch) -> None:
    captured = {}

    def fake_http_json(url, *, payload=None, api_key=None, timeout=180):
        captured["url"] = url
        captured["payload"] = payload
        return (
            200,
            {
                "data": {
                    "id": "resp_nested",
                    "model": "openai/gpt-5.6-sol",
                    "provider": "OpenAI",
                    "output_text": '{"scenario_id":"ACCB-DEV-001"}',
                    "usage": {"input_tokens": 200, "output_tokens": 30, "total_tokens": 230},
                }
            },
            0.75,
        )

    monkeypatch.setattr(pilot, "http_json", fake_http_json)
    endpoint = {
        "api_transport": "responses",
        "tag": "openai",
        "supported_parameters": ["reasoning", "include_reasoning", "response_format"],
    }
    body, elapsed = retry.retry_chat(
        "secret",
        "openai/gpt-5.6-sol",
        endpoint,
        [
            {"role": "system", "content": "system contract"},
            {"role": "user", "content": "Return JSON"},
        ],
        max_tokens=retry.RETRY_MAX_OUTPUT_TOKENS,
        timeout=120,
    )
    payload = captured["payload"]
    assert captured["url"] == f"{pilot.BASE_URL}/responses"
    assert payload["provider"] == {"only": ["openai"], "allow_fallbacks": False}
    assert payload["reasoning"] == {"effort": "low"}
    assert payload["include_reasoning"] is False
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["instructions"] == "system contract"
    assert pilot.response_text(body) == '{"scenario_id":"ACCB-DEV-001"}'
    assert pilot.usage(body) == (200, 30, 230)
    assert body["_routerai_transport"] == "responses"
    assert body["_retry_visible_text_present"] is True
    assert elapsed == 0.75


def test_responses_usage_survives_missing_visible_text() -> None:
    body = retry._normalize_responses_body(
        {
            "id": "resp_usage_only",
            "usage": {"input_tokens": 500, "output_tokens": 8192, "total_tokens": 8692},
            "output": [{"type": "reasoning", "summary": []}],
        }
    )
    assert pilot.usage(body) == (500, 8192, 8692)
    assert body["_retry_visible_text_present"] is False
    try:
        retry.retry_response_text(body)
    except pilot.IntegrationError as exc:
        message = str(exc)
    else:
        raise AssertionError("usage-only body must not be accepted as a candidate trace")
    assert '"completion_tokens":8192' in message
    assert "no visible final text after usage accounting" in message


def test_api_error_is_sanitized_and_not_treated_as_generated_text() -> None:
    body = {
        "error": {
            "type": "invalid_request_error",
            "code": "unsupported_parameter",
            "param": "response_format",
            "message": "SENSITIVE_SENTINEL_4713",
        }
    }
    try:
        retry._normalize_responses_body(body)
    except pilot.IntegrationError as exc:
        message = str(exc)
    else:
        raise AssertionError("API error without usage must fail before benchmark parsing")
    assert "invalid_request_error" in message
    assert "unsupported_parameter" in message
    assert "response_format" in message
    assert "SENSITIVE_SENTINEL_4713" not in message


def test_retry_never_uses_reasoning_content_as_final_answer() -> None:
    sentinel = "SENSITIVE_SENTINEL_4713"
    body = {
        "choices": [
            {
                "message": {
                    "content": "",
                    "reasoning_content": sentinel,
                }
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }
    try:
        retry._chat_visible_text(body)
    except pilot.IntegrationError as exc:
        message = str(exc)
    else:
        raise AssertionError("reasoning-only body must not be accepted as a final answer")
    assert sentinel not in message
    assert "reasoning_content" not in message
    assert "no visible final text" in message
    assert '"completion_tokens":20' in message
