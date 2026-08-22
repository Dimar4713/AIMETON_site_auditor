#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import accb_routerai_live_entrypoint as live
import accb_routerai_live_pilot as pilot
import accb_routerai_retry_v2_entrypoint as _impl

# Backward-compatible exports used by the existing retry tests and by historical
# three-model receipts. The implementation remains frozen in retry_v2.
RETRY_MODELS = _impl.RETRY_MODELS
PRIOR_SUCCESSFUL_MODELS = _impl.PRIOR_SUCCESSFUL_MODELS
SOURCE_CALIBRATION_RUN = _impl.SOURCE_CALIBRATION_RUN
RETRY_OF_RUN = _impl.RETRY_OF_RUN
REASONING_EFFORT = _impl.REASONING_EFFORT
RETRY_MAX_OUTPUT_TOKENS = _impl.RETRY_MAX_OUTPUT_TOKENS
_safe_error_summary = _impl._safe_error_summary
_usage_summary = _impl._usage_summary
_visible_text = _impl._visible_text
_normalize_responses_body = _impl._normalize_responses_body
_common_generation_controls = _impl._common_generation_controls
retry_chat = _impl.retry_chat
retry_response_text = _impl.retry_response_text
_chat_visible_text = _impl._chat_visible_text
_finalize_retry_metadata = _impl._finalize_retry_metadata

TRIGGER_PATH = Path("docs/research/ACCB_ROUTERAI_LIVE_TRIGGER_2026-08-22.json")
SOL_MODEL = "openai/gpt-5.6-sol"
SOL_RETRY_MODELS = [SOL_MODEL]
SOL_SOURCE_RUN = 32595531554
SOL_PROBE_PROMPT_RESERVE = 8_000
SOL_PROBE_COMPLETION_RESERVE = 4
SOL_MAX_OUTPUT_TOKENS = RETRY_MAX_OUTPUT_TOKENS
SOL_EVIDENCE_LABEL = "ACCB RouterAI Sol-only completion gate"

FOUR_MODEL_EVIDENCE = {
    "qwen/qwen3.7-plus": {
        "source_run": 32584584044,
        "ACI": 1.0,
        "ACI_min": 1.0,
        "critical_failure_count": 0,
    },
    "z-ai/glm-5.2": {
        "source_run": 32584584044,
        "ACI": 0.916667,
        "ACI_min": 0.5,
        "critical_failure_count": 1,
    },
    "moonshotai/kimi-k3": {
        "source_run": SOL_SOURCE_RUN,
        "ACI": 0.833333,
        "ACI_min": 0.5,
        "critical_failure_count": 2,
    },
    "deepseek/deepseek-v4-pro-0813": {
        "source_run": SOL_SOURCE_RUN,
        "ACI": 0.716667,
        "ACI_min": 0.0,
        "critical_failure_count": 2,
    },
}

_ORIGINAL_USAGE = pilot.usage
_SOL_PROBE_USAGE_FALLBACK_USED = False
_SOL_LIVE_RECEIPT: dict[str, Any] | None = None


def _trigger_retry_models(path: Path = TRIGGER_PATH) -> list[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return list(RETRY_MODELS)
    raw = payload.get("retry_models")
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        return list(RETRY_MODELS)
    return list(raw)


def _write_workflow_evidence_override() -> None:
    """Override the historical retry-failed-three shell defaults for later steps.

    The workflow intentionally keeps the already-governed execution_mode so the
    merge trigger is not widened. GitHub applies GITHUB_ENV updates to following
    steps, therefore evidence publishing sees one expected model and the Sol-only
    label even though the dispatch shell entered the historical retry branch.
    """
    env_path = os.getenv("GITHUB_ENV", "").strip()
    if not env_path:
        return
    with open(env_path, "a", encoding="utf-8") as handle:
        handle.write("ACCB_EXPECTED_MODELS=1\n")
        handle.write(f"ACCB_EVIDENCE_LABEL={SOL_EVIDENCE_LABEL}\n")


def _sol_chat(
    api_key: str,
    model_id: str,
    endpoint: dict[str, Any],
    messages: list[dict[str, str]],
    *,
    max_tokens: int,
    temperature: float = 0.0,
    timeout: int = 240,
) -> tuple[dict[str, Any], float]:
    """Use the v3 transport but tolerate only the known Sol probe anomaly.

    A successful Responses envelope with no usage on the <=16-token auxiliary
    tokenizer probe is marked for conservative reservation. API errors still
    fail in retry_chat before reaching this function. The real benchmark call
    never receives this exemption: its usage remains mandatory in pilot.main().
    """
    global _SOL_PROBE_USAGE_FALLBACK_USED, _SOL_LIVE_RECEIPT

    body, elapsed = _impl.retry_chat(
        api_key,
        model_id,
        endpoint,
        messages,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout=timeout,
    )
    summary = _impl._usage_summary(body)
    prompt = summary.get("prompt_tokens")
    completion = summary.get("completion_tokens")

    if max_tokens <= 16 and prompt is None and completion is None:
        body["_sol_probe_usage_missing"] = True
        _SOL_PROBE_USAGE_FALLBACK_USED = True
        return body, elapsed

    if max_tokens > 16 and isinstance(prompt, int) and isinstance(completion, int):
        total = summary.get("total_tokens")
        if not isinstance(total, int):
            total = prompt + completion
        _SOL_LIVE_RECEIPT = {
            "usage": {
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "total_tokens": total,
            },
            "estimated_cost_rub": round(pilot.estimated_cost(endpoint, prompt, completion), 6),
            "elapsed_seconds": round(elapsed, 6),
            "provider_metadata": pilot.safe_provider_metadata(body),
        }
    return body, elapsed


def _sol_usage(body: dict[str, Any]) -> tuple[int | None, int | None, int | None]:
    prompt, completion, total = _ORIGINAL_USAGE(body)
    if (
        body.get("_sol_probe_usage_missing") is True
        and prompt is None
        and completion is None
    ):
        # These numbers are a budget reservation only. They are deliberately
        # removed from the persisted scientific receipt in _finalize_sol_metadata.
        return (
            SOL_PROBE_PROMPT_RESERVE,
            SOL_PROBE_COMPLETION_RESERVE,
            SOL_PROBE_PROMPT_RESERVE + SOL_PROBE_COMPLETION_RESERVE,
        )
    return prompt, completion, total


def _known_cost_from_payload(payload: dict[str, Any]) -> float:
    known = 0.0
    for row in payload.get("rows") or []:
        if not isinstance(row, dict):
            continue
        live_cost = row.get("estimated_cost_rub")
        if isinstance(live_cost, (int, float)) and not isinstance(live_cost, bool):
            known += float(live_cost)
        probe = row.get("task_probe")
        if not isinstance(probe, dict):
            continue
        if probe.get("usage_status") == "missing_reserved_upper_bound":
            continue
        probe_cost = probe.get("estimated_cost_rub")
        if isinstance(probe_cost, (int, float)) and not isinstance(probe_cost, bool):
            known += float(probe_cost)
    return known


def _finalize_sol_metadata(result_path: Path) -> None:
    if not result_path.exists():
        return
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload["schema_version"] = "0.6-sol-only"
    payload["retry_scope"] = "sol-only"
    payload["retry_of_run"] = SOL_SOURCE_RUN
    payload["source_calibration_runs"] = [32584584044, SOL_SOURCE_RUN]
    payload["prior_successful_models_reused_not_repeated"] = FOUR_MODEL_EVIDENCE
    payload["retry_models"] = list(SOL_RETRY_MODELS)
    payload["probe_policy"] = {
        "purpose": "auxiliary task-payload tokenizer measurement",
        "visible_final_text_required": False,
        "usage_preferred": True,
        "missing_usage_behavior": (
            "Sol Responses probe may continue only after reserving the conservative 8000-input/4-output upper bound; "
            "persisted L_task_payload remains UNKNOWN rather than synthetic"
        ),
        "live_response_usage_required": True,
    }
    payload["accounting_policy"] = (
        "The Sol live envelope must expose usage before candidate parsing. If the auxiliary Responses probe omits usage, "
        "the budget guard reserves its full 8000-input/4-output upper bound; synthetic reserve tokens are never retained "
        "as scientific measurements."
    )

    for row in payload.get("rows") or []:
        if not isinstance(row, dict) or row.get("model_identifier") != SOL_MODEL:
            continue
        endpoint = row.get("endpoint") if isinstance(row.get("endpoint"), dict) else {}
        probe = row.get("task_probe")
        if _SOL_PROBE_USAGE_FALLBACK_USED and isinstance(probe, dict):
            reserved = pilot.estimated_cost(
                endpoint,
                SOL_PROBE_PROMPT_RESERVE,
                SOL_PROBE_COMPLETION_RESERVE,
            )
            probe["prompt_tokens"] = None
            probe["completion_tokens"] = None
            probe.pop("total_tokens", None)
            probe["estimated_cost_rub"] = None
            probe["usage_status"] = "missing_reserved_upper_bound"
            probe["budget_reserved_upper_bound_rub"] = round(reserved, 6)

        # If visible-answer parsing fails after a billable Sol envelope, pilot.main
        # catches the exception before row.update(). Restore sanitized usage/cost
        # from the already captured envelope so accounting is never lost again.
        if _SOL_LIVE_RECEIPT is not None:
            if not isinstance(row.get("usage"), dict):
                row["usage"] = dict(_SOL_LIVE_RECEIPT["usage"])
            if not isinstance(row.get("estimated_cost_rub"), (int, float)):
                row["estimated_cost_rub"] = _SOL_LIVE_RECEIPT["estimated_cost_rub"]
            row.setdefault("elapsed_seconds", _SOL_LIVE_RECEIPT["elapsed_seconds"])
            row.setdefault("provider_metadata", _SOL_LIVE_RECEIPT["provider_metadata"])
            row["usage_accounted_before_candidate_parse"] = True

        manifest = row.get("manifest")
        if isinstance(manifest, dict):
            lengths = manifest.get("lengths")
            if _SOL_PROBE_USAGE_FALLBACK_USED and isinstance(lengths, dict):
                lengths["L_task_payload"] = None
                lengths["L_visible_shell"] = None
                lengths["L_task_payload_status"] = "UNKNOWN: RouterAI Responses probe returned no usage"
            manifest["reasoning_mode"] = REASONING_EFFORT
            manifest["max_output_tokens"] = SOL_MAX_OUTPUT_TOKENS
            manifest["retry_of_run"] = SOL_SOURCE_RUN
            manifest["api_transport"] = endpoint.get("api_transport")

    payload["confirmed_accounted_spend_rub"] = round(_known_cost_from_payload(payload), 6)
    payload["budget_accounted_spend_rub"] = payload.get("estimated_spend_rub")
    payload["probe_usage_fallback_used"] = _SOL_PROBE_USAGE_FALLBACK_USED
    payload["scientific_claim_boundary"] = (
        "Fifth-model low-context calibration/integration evidence only; no universal ECC/AMCE threshold inference."
    )
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sol_main() -> int:
    global _SOL_PROBE_USAGE_FALLBACK_USED, _SOL_LIVE_RECEIPT
    _SOL_PROBE_USAGE_FALLBACK_USED = False
    _SOL_LIVE_RECEIPT = None
    _write_workflow_evidence_override()

    live.MAIN_MODELS = list(SOL_RETRY_MODELS)
    pilot.MODELS = list(SOL_RETRY_MODELS)
    pilot.MAX_OUTPUT_TOKENS = SOL_MAX_OUTPUT_TOKENS
    pilot.chat = _sol_chat
    pilot.response_text = _impl.retry_response_text
    pilot.usage = _sol_usage
    pilot.rub_per_token = live.safe_rub_per_token

    cache, rc = live.admission_preflight()
    if rc != 0:
        return rc

    def cached_endpoint_census(model_id: str) -> dict[str, Any]:
        try:
            return cache[model_id]
        except KeyError as exc:
            raise pilot.IntegrationError(f"Sol-only model was not admitted: {model_id}") from exc

    pilot.endpoint_census = cached_endpoint_census
    result_rc = pilot.main()
    result_path = Path(pilot.required_env("ACCB_RESULT_PATH"))
    live.finalize_result_transport_metadata(result_path)
    _finalize_sol_metadata(result_path)
    return result_rc


def main() -> int:
    retry_models = _trigger_retry_models()
    if retry_models == SOL_RETRY_MODELS:
        return sol_main()
    if retry_models != list(RETRY_MODELS):
        raise pilot.IntegrationError(
            f"unsupported bounded retry model set: {retry_models!r}; expected historical three or Sol-only"
        )
    return _impl.main()


if __name__ == "__main__":
    raise SystemExit(main())
