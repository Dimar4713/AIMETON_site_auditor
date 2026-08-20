from __future__ import annotations

import json
from pathlib import Path

from app.verifier_model_profiles import VerifierProfileError
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


def _body(top_logprobs: list[dict], *, content: str = "A", model: str = "openai/gpt-4o-mini") -> dict:
    return {
        "id": "chatcmpl-test",
        "model": model,
        "provider": "test-provider",
        "choices": [
            {
                "message": {"content": content},
                "logprobs": {
                    "content": [
                        {
                            "token": top_logprobs[0]["token"],
                            "logprob": top_logprobs[0]["logprob"],
                            "top_logprobs": top_logprobs,
                        }
                    ]
                },
            }
        ],
        "usage": {
            "prompt_tokens": 64,
            "completion_tokens": 2,
            "total_tokens": 66,
        },
    }


def _unconstrained_singleton_body(model: str = "openai/gpt-4o-mini") -> dict:
    return _body(
        [
            {"token": "A", "logprob": -0.05},
            {"token": " ordinary", "logprob": -1.0},
            {"token": " token", "logprob": -1.7},
        ],
        model=model,
    )


def _structured_qualified_body(model: str = "openai/gpt-4o-mini") -> dict:
    return _body(
        [
            {"token": '"A"', "logprob": -0.2},
            {"token": '"B"', "logprob": -0.8},
            {"token": '"C"', "logprob": -1.6},
        ],
        content='{"score":"A"}',
        model=model,
    )


def _configure(monkeypatch, tmp_path: Path, profile: str = "routerai-gpt4o-mini") -> Path:
    result_path = tmp_path / "probe.json"
    monkeypatch.setenv("ROUTERAI_API_KEY", "secret-value-must-not-leak")
    monkeypatch.setenv("VERIFIER_PROFILE", profile)
    monkeypatch.setenv("VERIFIER_MAX_BUDGET_RUB", "100")
    monkeypatch.setenv("VERIFIER_RESULT_PATH", str(result_path))
    return result_path


def test_live_probe_compares_unconstrained_and_structured_paths(monkeypatch, tmp_path: Path):
    result_path = _configure(monkeypatch, tmp_path)

    def fake_urlopen(request, timeout):
        payload = json.loads(request.data.decode("utf-8"))
        if "response_format" in payload:
            return _FakeResponse(_structured_qualified_body())
        return _FakeResponse(_unconstrained_singleton_body())

    monkeypatch.setattr(probe.urllib.request, "urlopen", fake_urlopen)

    assert probe.main() == 0
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "1.2"
    assert payload["profile_id"] == "routerai-gpt4o-mini"
    assert payload["requested_model"] == "openai/gpt-4o-mini"
    assert payload["qualification_status"] == "runtime_qualified"
    assert payload["provider_calls"] == 2
    unconstrained = payload["probe_modes"]["unconstrained_top_logprobs"]
    structured = payload["probe_modes"]["structured_json_schema"]
    assert unconstrained["qualification_status"] == "runtime_degraded"
    assert unconstrained["max_score_support"] == 1
    assert structured["qualification_status"] == "runtime_qualified"
    assert structured["max_score_support"] == 3
    assert payload["required_min_distinct_score_support"] == 2
    assert payload["raw_response_saved"] is False
    assert payload["client_release_authority"] is False
    assert payload["hard_gate_override"] is False
    assert payload["actual_estimated_cost_rub"] < 0.01
    rendered = result_path.read_text(encoding="utf-8")
    assert "secret-value-must-not-leak" not in rendered
    assert "choices" not in payload
    assert "messages" not in payload


def test_qwen_profile_changes_model_and_pricing_without_code_change(monkeypatch, tmp_path: Path):
    result_path = _configure(monkeypatch, tmp_path, profile="routerai-qwen35-9b")
    seen_models: list[str] = []

    def fake_urlopen(request, timeout):
        payload = json.loads(request.data.decode("utf-8"))
        seen_models.append(payload["model"])
        model = payload["model"]
        if "response_format" in payload:
            return _FakeResponse(_structured_qualified_body(model))
        return _FakeResponse(_unconstrained_singleton_body(model))

    monkeypatch.setattr(probe.urllib.request, "urlopen", fake_urlopen)

    assert probe.main() == 0
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert seen_models == ["qwen/qwen3.5-9b", "qwen/qwen3.5-9b"]
    assert payload["profile_id"] == "routerai-qwen35-9b"
    assert payload["requested_model"] == "qwen/qwen3.5-9b"
    assert payload["pricing_snapshot_rub_per_million"] == {"input": 11.0, "output": 16.0}


def test_live_probe_rejects_budget_above_owner_cap(monkeypatch, tmp_path: Path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setenv("VERIFIER_MAX_BUDGET_RUB", "100.01")

    try:
        probe.main()
    except RuntimeError as exc:
        assert "must be in (0, 100]" in str(exc)
    else:
        raise AssertionError("budget above owner cap must fail closed")


def test_live_probe_rejects_unknown_profile(monkeypatch, tmp_path: Path):
    _configure(monkeypatch, tmp_path, profile="routerai-unreviewed-random-model")

    try:
        probe.main()
    except VerifierProfileError as exc:
        assert "unknown verifier profile" in str(exc)
    else:
        raise AssertionError("unallowlisted model profile must fail closed")
