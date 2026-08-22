from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import accb_routerai_live_pilot as pilot
import accb_routerai_retry_entrypoint as retry


def test_sol_retry_is_exactly_one_model_and_freezes_four_scores() -> None:
    assert retry.SOL_RETRY_MODELS == ["openai/gpt-5.6-sol"]
    assert retry.SOL_MAX_OUTPUT_TOKENS == 8192
    assert set(retry.FOUR_MODEL_EVIDENCE) == {
        "qwen/qwen3.7-plus",
        "z-ai/glm-5.2",
        "moonshotai/kimi-k3",
        "deepseek/deepseek-v4-pro-0813",
    }
    assert retry.SOL_MODEL not in retry.FOUR_MODEL_EVIDENCE


def test_trigger_model_set_selects_sol_only(tmp_path: Path) -> None:
    trigger = tmp_path / "trigger.json"
    trigger.write_text(json.dumps({"retry_models": [retry.SOL_MODEL]}), encoding="utf-8")
    assert retry._trigger_retry_models(trigger) == [retry.SOL_MODEL]


def test_sol_probe_missing_usage_gets_budget_marker_not_fake_scientific_usage(monkeypatch) -> None:
    retry._SOL_PROBE_USAGE_FALLBACK_USED = False

    def fake_retry_chat(*args, **kwargs):
        return {
            "choices": [{"message": {"role": "assistant", "content": ""}}],
            "usage": {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None},
            "_routerai_transport": "responses",
        }, 0.25

    monkeypatch.setattr(retry._impl, "retry_chat", fake_retry_chat)
    body, elapsed = retry._sol_chat(
        "secret",
        retry.SOL_MODEL,
        {"api_transport": "responses", "tag": "openai", "pricing": {"prompt": 0.1, "completion": 0.2}},
        [{"role": "user", "content": "probe"}],
        max_tokens=4,
        timeout=30,
    )
    assert elapsed == 0.25
    assert body["_sol_probe_usage_missing"] is True
    assert retry._SOL_PROBE_USAGE_FALLBACK_USED is True
    assert retry._sol_usage(body) == (8000, 4, 8004)
    # A missing-usage live envelope is never granted the probe exemption.
    assert retry._sol_usage({"usage": {"prompt_tokens": None, "completion_tokens": None}}) == (None, None, None)


def test_sol_live_receipt_is_captured_before_candidate_parse(monkeypatch) -> None:
    retry._SOL_LIVE_RECEIPT = None

    def fake_retry_chat(*args, **kwargs):
        return {
            "model": retry.SOL_MODEL,
            "provider": "OpenAI",
            "id": "resp_test",
            "choices": [{"message": {"role": "assistant", "content": ""}}],
            "usage": {"prompt_tokens": 40000, "completion_tokens": 2000, "total_tokens": 42000},
            "_routerai_transport": "responses",
        }, 1.5

    monkeypatch.setattr(retry._impl, "retry_chat", fake_retry_chat)
    monkeypatch.setattr(pilot, "estimated_cost", lambda endpoint, prompt, completion: 12.5)
    body, _ = retry._sol_chat(
        "secret",
        retry.SOL_MODEL,
        {"api_transport": "responses", "tag": "openai"},
        [{"role": "user", "content": "live"}],
        max_tokens=8192,
        timeout=30,
    )
    assert body["usage"]["prompt_tokens"] == 40000
    assert retry._SOL_LIVE_RECEIPT == {
        "usage": {"prompt_tokens": 40000, "completion_tokens": 2000, "total_tokens": 42000},
        "estimated_cost_rub": 12.5,
        "elapsed_seconds": 1.5,
        "provider_metadata": {"model": retry.SOL_MODEL, "provider": "OpenAI", "id": "resp_test"},
    }


def test_finalize_sol_removes_synthetic_probe_tokens_and_restores_live_accounting(tmp_path: Path, monkeypatch) -> None:
    result = tmp_path / "result.json"
    payload = {
        "schema_version": "0.1",
        "experiment_id": "ACCB-ROUTERAI-CAL-2026-08-22-LOW-001",
        "estimated_spend_rub": 14.25,
        "rows": [
            {
                "model_identifier": retry.SOL_MODEL,
                "endpoint": {
                    "api_transport": "responses",
                    "pricing": {"prompt": 0.001, "completion": 0.002},
                    "variable_pricings": [],
                },
                "status": "integration_error",
                "error": "IntegrationError: no visible final text",
                "task_probe": {
                    "prompt_tokens": 8000,
                    "completion_tokens": 4,
                    "estimated_cost_rub": 8.008,
                    "provider_metadata": {"provider": "OpenAI"},
                },
            }
        ],
    }
    result.write_text(json.dumps(payload), encoding="utf-8")
    retry._SOL_PROBE_USAGE_FALLBACK_USED = True
    retry._SOL_LIVE_RECEIPT = {
        "usage": {"prompt_tokens": 40000, "completion_tokens": 3000, "total_tokens": 43000},
        "estimated_cost_rub": 6.25,
        "elapsed_seconds": 9.0,
        "provider_metadata": {"provider": "OpenAI", "id": "resp_live"},
    }
    monkeypatch.setattr(pilot, "estimated_cost", lambda endpoint, prompt, completion: 8.008)

    retry._finalize_sol_metadata(result)
    final = json.loads(result.read_text(encoding="utf-8"))
    row = final["rows"][0]
    probe = row["task_probe"]
    assert probe["prompt_tokens"] is None
    assert probe["completion_tokens"] is None
    assert probe["estimated_cost_rub"] is None
    assert probe["usage_status"] == "missing_reserved_upper_bound"
    assert probe["budget_reserved_upper_bound_rub"] == 8.008
    assert row["usage"] == {"prompt_tokens": 40000, "completion_tokens": 3000, "total_tokens": 43000}
    assert row["estimated_cost_rub"] == 6.25
    assert row["usage_accounted_before_candidate_parse"] is True
    assert final["confirmed_accounted_spend_rub"] == 6.25
    assert final["budget_accounted_spend_rub"] == 14.25
    assert final["prior_successful_models_reused_not_repeated"] == retry.FOUR_MODEL_EVIDENCE


def test_workflow_evidence_override_is_one_model(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / "github-env"
    monkeypatch.setenv("GITHUB_ENV", str(env_file))
    retry._write_workflow_evidence_override()
    content = env_file.read_text(encoding="utf-8")
    assert "ACCB_EXPECTED_MODELS=1\n" in content
    assert f"ACCB_EVIDENCE_LABEL={retry.SOL_EVIDENCE_LABEL}\n" in content
