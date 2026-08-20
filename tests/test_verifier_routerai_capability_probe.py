from __future__ import annotations

import json
from pathlib import Path

from scripts import verifier_routerai_capability_probe as probe


class _FakeResponse:
    status = 200

    def __init__(self, payload: dict):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def _qualified_body() -> dict:
    return {
        "id": "chatcmpl-test",
        "model": "openai/gpt-4o-mini",
        "provider": "test-provider",
        "choices": [
            {
                "message": {"content": "A"},
                "logprobs": {
                    "content": [
                        {
                            "token": "A",
                            "logprob": -0.05,
                            "top_logprobs": [
                                {"token": "A", "logprob": -0.05},
                                {"token": "B", "logprob": -1.4},
                                {"token": "C", "logprob": -2.2},
                            ],
                        }
                    ]
                },
            }
        ],
        "usage": {
            "prompt_tokens": 64,
            "completion_tokens": 1,
            "total_tokens": 65,
        },
    }


def test_live_probe_writes_only_sanitized_capability_evidence(monkeypatch, tmp_path: Path):
    result_path = tmp_path / "probe.json"
    monkeypatch.setenv("ROUTERAI_API_KEY", "secret-value-must-not-leak")
    monkeypatch.setenv("VERIFIER_MODEL", "openai/gpt-4o-mini")
    monkeypatch.setenv("VERIFIER_MAX_BUDGET_RUB", "100")
    monkeypatch.setenv("VERIFIER_RESULT_PATH", str(result_path))
    monkeypatch.setattr(
        probe.urllib.request,
        "urlopen",
        lambda request, timeout: _FakeResponse(_qualified_body()),
    )

    assert probe.main() == 0
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert payload["qualification_status"] == "runtime_qualified"
    assert payload["provider_calls"] == 1
    assert payload["raw_response_saved"] is False
    assert payload["client_release_authority"] is False
    assert payload["hard_gate_override"] is False
    assert payload["actual_estimated_cost_rub"] < 0.01
    assert "secret-value-must-not-leak" not in result_path.read_text(encoding="utf-8")
    assert "choices" not in payload
    assert "messages" not in payload


def test_live_probe_rejects_budget_above_owner_cap(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("ROUTERAI_API_KEY", "secret")
    monkeypatch.setenv("VERIFIER_MODEL", "openai/gpt-4o-mini")
    monkeypatch.setenv("VERIFIER_MAX_BUDGET_RUB", "100.01")
    monkeypatch.setenv("VERIFIER_RESULT_PATH", str(tmp_path / "probe.json"))

    try:
        probe.main()
    except RuntimeError as exc:
        assert "must be in (0, 100]" in str(exc)
    else:
        raise AssertionError("budget above owner cap must fail closed")


def test_live_probe_is_pinned_to_owner_selected_model(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("ROUTERAI_API_KEY", "secret")
    monkeypatch.setenv("VERIFIER_MODEL", "openai/gpt-4o")
    monkeypatch.setenv("VERIFIER_MAX_BUDGET_RUB", "100")
    monkeypatch.setenv("VERIFIER_RESULT_PATH", str(tmp_path / "probe.json"))

    try:
        probe.main()
    except RuntimeError as exc:
        assert "pinned to openai/gpt-4o-mini" in str(exc)
    else:
        raise AssertionError("model drift must fail closed")
