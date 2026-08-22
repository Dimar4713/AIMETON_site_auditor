from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

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


def test_recursive_usage_finds_nested_responses_meta_usage() -> None:
    raw = {
        "id": "resp_1",
        "response": {
            "meta": {
                "usage": {
                    "input_tokens": 1234,
                    "output_tokens": 56,
                    "total_tokens": 1290,
                }
            }
        },
    }
    assert retry._recursive_usage(raw) == (1234, 56, 1290, "$.response.meta.usage")


def test_recursive_usage_accepts_prompt_completion_names() -> None:
    raw = {"data": [{"billing": {"prompt_tokens": 321, "completion_tokens": 7}}]}
    assert retry._recursive_usage(raw) == (321, 7, 328, "$.data[0].billing")


def test_safe_usage_diagnostic_never_retains_text_or_reasoning_values() -> None:
    raw = {
        "id": "resp_safe",
        "output": [{"type": "message", "content": [{"type": "output_text", "text": "SECRET"}]}],
        "reasoning": {"text": "PRIVATE"},
        "meta": {"usage": {"cost": 1.25}},
    }
    diagnostic = retry._safe_usage_diagnostic(raw)
    encoded = json.dumps(diagnostic, ensure_ascii=False)
    assert "SECRET" not in encoded
    assert "PRIVATE" not in encoded
    assert "resp_safe" in encoded
    assert "$.meta.usage" in encoded


def test_probe_without_recursive_usage_fails_closed_before_live() -> None:
    retry._SOL_MISSING_USAGE_DIAGNOSTIC = None
    body = retry._normalize_sol_responses(
        {"id": "resp_probe", "output": []},
        live_call=False,
    )
    assert body["_sol_usage_missing"] is True
    assert body["_sol_usage_missing_phase"] == "probe"
    with pytest.raises(pilot.IntegrationError, match="probe returned no discoverable token usage"):
        retry._sol_usage(body)


def test_nested_probe_usage_is_normalized_without_visible_text_requirement() -> None:
    retry._SOL_MISSING_USAGE_DIAGNOSTIC = None
    body = retry._normalize_sol_responses(
        {
            "id": "resp_probe",
            "data": {"meta": {"usage": {"input_tokens": 567, "output_tokens": 4}}},
            "output": [],
        },
        live_call=False,
    )
    assert retry._sol_usage(body) == (567, 4, 571)
    assert body["choices"][0]["message"]["content"] == ""
    assert body["_sol_usage_path"] == "$.data.meta.usage"


def test_sol_chat_captures_nested_live_usage_before_visible_parse(monkeypatch) -> None:
    retry._SOL_LIVE_RECEIPT = None

    raw = {
        "id": "resp_live",
        "model": retry.SOL_MODEL,
        "provider": "OpenAI",
        "response": {
            "usage": {"input_tokens": 40000, "output_tokens": 2000, "total_tokens": 42000},
            "output": [],
        },
    }

    def fake_http_json(*args, **kwargs):
        return 200, raw, 1.5

    monkeypatch.setattr(pilot, "http_json", fake_http_json)
    monkeypatch.setattr(pilot, "estimated_cost", lambda endpoint, prompt, completion: 12.5)
    body, elapsed = retry._sol_chat(
        "secret",
        retry.SOL_MODEL,
        {
            "api_transport": "responses",
            "tag": "openai",
            "supported_parameters": [],
        },
        [{"role": "user", "content": "live"}],
        max_tokens=8192,
        timeout=30,
    )
    assert elapsed == 1.5
    assert retry._sol_usage(body) == (40000, 2000, 42000)
    assert retry._SOL_LIVE_RECEIPT == {
        "usage": {"prompt_tokens": 40000, "completion_tokens": 2000, "total_tokens": 42000},
        "usage_path": "$.response.usage",
        "estimated_cost_rub": 12.5,
        "elapsed_seconds": 1.5,
        "provider_metadata": {"model": retry.SOL_MODEL, "provider": "OpenAI", "id": "resp_live"},
    }


def test_finalize_marks_missing_usage_spend_unknown_not_zero(tmp_path: Path) -> None:
    result = tmp_path / "result.json"
    result.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "experiment_id": "ACCB-ROUTERAI-CAL-2026-08-22-LOW-001",
                "estimated_spend_rub": 0.0,
                "rows": [
                    {
                        "model_identifier": retry.SOL_MODEL,
                        "endpoint": {"api_transport": "responses", "tag": "openai"},
                        "status": "integration_error",
                        "error": "IntegrationError: task probe returned no token usage",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    retry._SOL_MISSING_USAGE_DIAGNOSTIC = {
        "phase": "probe",
        "top_level_keys": ["id", "output"],
        "usage_related_objects": [],
        "request_ids": [{"path": "$.id", "value": "resp_missing"}],
    }
    retry._SOL_LIVE_RECEIPT = None
    retry._SOL_USAGE_PATHS["probe"] = None
    retry._SOL_USAGE_PATHS["live"] = None

    retry._finalize_sol_metadata(result)
    final = json.loads(result.read_text(encoding="utf-8"))
    row = final["rows"][0]
    assert final["estimated_spend_rub"] is None
    assert "UNKNOWN/unreconciled" in final["current_run_spend_status"]
    assert row["usage_accounting_status"] == "UNKNOWN/unreconciled"
    assert final["confirmed_accounted_spend_rub"] == 0.0
    assert final["safe_usage_diagnostic"]["request_ids"][0]["value"] == "resp_missing"


def test_finalize_restores_live_accounting_after_visible_parse_failure(tmp_path: Path) -> None:
    result = tmp_path / "result.json"
    result.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "experiment_id": "ACCB-ROUTERAI-CAL-2026-08-22-LOW-001",
                "estimated_spend_rub": 0.0,
                "rows": [
                    {
                        "model_identifier": retry.SOL_MODEL,
                        "endpoint": {"api_transport": "responses", "tag": "openai"},
                        "status": "integration_error",
                        "error": "IntegrationError: no visible final text",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    retry._SOL_MISSING_USAGE_DIAGNOSTIC = None
    retry._SOL_LIVE_RECEIPT = {
        "usage": {"prompt_tokens": 40000, "completion_tokens": 3000, "total_tokens": 43000},
        "usage_path": "$.meta.usage",
        "estimated_cost_rub": 6.25,
        "elapsed_seconds": 9.0,
        "provider_metadata": {"provider": "OpenAI", "id": "resp_live"},
    }
    retry._SOL_USAGE_PATHS["probe"] = "$.usage"
    retry._SOL_USAGE_PATHS["live"] = "$.meta.usage"

    retry._finalize_sol_metadata(result)
    final = json.loads(result.read_text(encoding="utf-8"))
    row = final["rows"][0]
    assert row["usage"] == {"prompt_tokens": 40000, "completion_tokens": 3000, "total_tokens": 43000}
    assert row["estimated_cost_rub"] == 6.25
    assert row["usage_accounted_before_candidate_parse"] is True
    assert row["usage_path"] == "$.meta.usage"
    assert final["confirmed_accounted_spend_rub"] == 6.25


def test_workflow_evidence_override_is_one_model(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / "github-env"
    monkeypatch.setenv("GITHUB_ENV", str(env_file))
    retry._write_workflow_evidence_override()
    content = env_file.read_text(encoding="utf-8")
    assert "ACCB_EXPECTED_MODELS=1\n" in content
    assert f"ACCB_EVIDENCE_LABEL={retry.SOL_EVIDENCE_LABEL}\n" in content
