#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

import accb_routerai_live_pilot as pilot

MAIN_MODELS = [
    "z-ai/glm-5.2",
    "deepseek/deepseek-v4-pro-0813",
    "qwen/qwen3.7-plus",
    "moonshotai/kimi-k3",
    "openai/gpt-5.6-sol",
]
REPLACEMENTS = {
    "moonshotai/kimi-k2.6": {
        "replacement": "moonshotai/kimi-k3",
        "reason": "RouterAI runtime endpoint census on run 32581019920 exposed no healthy chat endpoint >=128K for Kimi K2.6; public catalog still advertised 262K, so runtime truth wins for admission.",
    }
}
MIN_CONTEXT = 128_000
ADMISSION_LIVE_PROMPT_UPPER = 80_000
ADMISSION_PROBE_PROMPT_UPPER = 8_000


def _positive_number(raw: Any, *, label: str) -> float:
    if isinstance(raw, bool) or raw is None:
        raise pilot.IntegrationError(f"missing/invalid RouterAI price: {label}={raw!r}")
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise pilot.IntegrationError(f"unparseable RouterAI price: {label}={raw!r}") from exc
    if not math.isfinite(value) or value <= 0:
        raise pilot.IntegrationError(f"non-positive/non-finite RouterAI price: {label}={raw!r}")
    return value


def _threshold(raw: Any, *, label: str) -> int:
    if isinstance(raw, bool) or raw is None:
        raise pilot.IntegrationError(f"missing/invalid RouterAI threshold: {label}={raw!r}")
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise pilot.IntegrationError(f"unparseable RouterAI threshold: {label}={raw!r}") from exc
    if not math.isfinite(value) or value < 0 or not value.is_integer():
        raise pilot.IntegrationError(f"invalid RouterAI threshold: {label}={raw!r}")
    return int(value)


def safe_rub_per_token(endpoint: dict[str, Any], key: str, prompt_tokens: int) -> float:
    if key not in {"prompt", "completion"}:
        raise pilot.IntegrationError(f"unsupported pricing key: {key}")
    pricing = endpoint.get("pricing")
    if not isinstance(pricing, dict):
        raise pilot.IntegrationError("RouterAI endpoint has no pricing object")
    result = _positive_number(pricing.get(key), label=f"base.{key}")

    variable = endpoint.get("variable_pricings") or []
    if not isinstance(variable, list):
        raise pilot.IntegrationError("RouterAI variable_pricings is not a list")
    for index, row in enumerate(variable):
        if not isinstance(row, dict):
            raise pilot.IntegrationError(f"RouterAI variable pricing row is not an object: index={index}")
        if row.get("type") != "prompt-threshold":
            continue
        threshold = _threshold(row.get("threshold"), label=f"variable[{index}].threshold")
        if prompt_tokens <= threshold:
            continue
        # RouterAI documents prompt-threshold rows that can override only the prompt
        # price. A missing completion override means the base completion price remains.
        if key in row:
            result = _positive_number(row.get(key), label=f"variable[{index}].{key}")
        elif key == "prompt":
            raise pilot.IntegrationError(
                f"RouterAI prompt-threshold row omits prompt price: index={index}, threshold={threshold}"
            )
    return result


def _endpoint_observation(endpoint: dict[str, Any]) -> dict[str, Any]:
    pricing = endpoint.get("pricing") if isinstance(endpoint.get("pricing"), dict) else {}
    return {
        "tag": endpoint.get("tag"),
        "provider_name": endpoint.get("provider_name"),
        "status": endpoint.get("status"),
        "context_length": endpoint.get("context_length"),
        "max_prompt_tokens": endpoint.get("max_prompt_tokens"),
        "max_completion_tokens": endpoint.get("max_completion_tokens"),
        "supported_apis": endpoint.get("supported_apis") or [],
        "pricing": {"prompt": pricing.get("prompt"), "completion": pricing.get("completion")},
    }


def detailed_endpoint_census(model_id: str) -> dict[str, Any]:
    author, slug = model_id.split("/", 1)
    _, body, elapsed = pilot.http_json(f"{pilot.BASE_URL}/models/{author}/{slug}/endpoints", timeout=60)
    data = body.get("data")
    if not isinstance(data, dict):
        raise pilot.IntegrationError(f"endpoint census missing data for {model_id}")
    endpoints = data.get("endpoints")
    if not isinstance(endpoints, list) or not endpoints:
        raise pilot.IntegrationError(f"endpoint census empty for {model_id}")

    observed = [_endpoint_observation(x) for x in endpoints if isinstance(x, dict)]
    candidates: list[dict[str, Any]] = []
    for endpoint in endpoints:
        if not isinstance(endpoint, dict):
            continue
        apis = endpoint.get("supported_apis") or []
        context_length = endpoint.get("context_length")
        status = endpoint.get("status")
        if "chat" not in apis:
            continue
        if not isinstance(context_length, int) or context_length < MIN_CONTEXT:
            continue
        if isinstance(status, int) and status < 0:
            continue
        candidates.append(endpoint)

    if not candidates:
        compact = json.dumps(observed[:12], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        raise pilot.IntegrationError(
            f"no healthy chat endpoint >={MIN_CONTEXT} for {model_id}; observed_endpoints={compact}"
        )

    chosen = candidates[0]
    pricing = chosen.get("pricing") if isinstance(chosen.get("pricing"), dict) else {}
    variable = chosen.get("variable_pricings") if isinstance(chosen.get("variable_pricings"), list) else []
    return {
        "model_id": model_id,
        "name": str(chosen.get("name") or ""),
        "provider_name": str(chosen.get("provider_name") or ""),
        "tag": str(chosen.get("tag") or ""),
        "country": chosen.get("country"),
        "context_length": chosen.get("context_length"),
        "max_prompt_tokens": chosen.get("max_prompt_tokens"),
        "max_completion_tokens": chosen.get("max_completion_tokens"),
        "quantization": chosen.get("quantization"),
        "pricing": {"prompt": pricing.get("prompt"), "completion": pricing.get("completion")},
        "variable_pricings": variable,
        "supported_parameters": chosen.get("supported_parameters") or [],
        "supported_apis": chosen.get("supported_apis") or [],
        "census_elapsed_seconds": round(elapsed, 6),
        "eligible_endpoint_count": len(candidates),
        "observed_endpoint_count": len(observed),
    }


def safe_endpoint_census(model_id: str) -> dict[str, Any]:
    endpoint = detailed_endpoint_census(model_id)
    tag = str(endpoint.get("tag") or "").strip()
    if not tag:
        raise pilot.IntegrationError(f"RouterAI endpoint for {model_id} has no provider tag; scored call cannot be pinned")
    context_length = endpoint.get("context_length")
    if not isinstance(context_length, int) or context_length < MIN_CONTEXT:
        raise pilot.IntegrationError(f"invalid context_length for {model_id}: {context_length!r}")

    safe_rub_per_token(endpoint, "prompt", 0)
    safe_rub_per_token(endpoint, "completion", 0)
    safe_rub_per_token(endpoint, "prompt", context_length)
    safe_rub_per_token(endpoint, "completion", context_length)
    return endpoint


def write_admission_failure(
    result_path: Path,
    *,
    max_budget_rub: float,
    architecture_sha: str,
    rows: list[dict[str, Any]],
    errors: list[str],
    upper_bound_rub: float,
) -> None:
    payload = {
        "schema_version": "0.2",
        "experiment_id": "ACCB-ROUTERAI-CAL-2026-08-22-LOW-001",
        "phase": "model_admission",
        "architecture_sha": architecture_sha,
        "site_auditor_sha": os.getenv("GITHUB_SHA"),
        "budget_ceiling_rub": max_budget_rub,
        "estimated_spend_rub": 0.0,
        "admission_upper_bound_rub": round(upper_bound_rub, 6),
        "models_requested": MAIN_MODELS,
        "models_scored": 0,
        "integration_errors": errors,
        "rows": rows,
        "model_replacements": REPLACEMENTS,
        "raw_provider_reasoning_saved": False,
        "scientific_claim_boundary": "Admission/calibration evidence only; no universal ECC/AMCE threshold inference.",
    }
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def admission_preflight() -> tuple[dict[str, dict[str, Any]], int]:
    result_path = Path(pilot.required_env("ACCB_RESULT_PATH"))
    max_budget_rub = float(pilot.required_env("ACCB_MAX_BUDGET_RUB"))
    architecture_sha = pilot.required_env("ACCB_ARCHITECTURE_SHA")

    cache: dict[str, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    total_upper = 0.0

    for model_id in MAIN_MODELS:
        row: dict[str, Any] = {"model_identifier": model_id, "status": "admission_started"}
        try:
            endpoint = safe_endpoint_census(model_id)
            probe_upper = pilot.estimated_cost(endpoint, ADMISSION_PROBE_PROMPT_UPPER, 4)
            live_upper = pilot.estimated_cost(endpoint, ADMISSION_LIVE_PROMPT_UPPER, pilot.MAX_OUTPUT_TOKENS)
            model_upper = probe_upper + live_upper
            total_upper += model_upper
            row.update({
                "status": "admitted",
                "endpoint": endpoint,
                "admission_cost_upper_bound_rub": round(model_upper, 6),
            })
            cache[model_id] = endpoint
        except Exception as exc:
            message = f"{model_id}: {type(exc).__name__}: {exc}"[:8000]
            row.update({"status": "admission_error", "error": message})
            errors.append(message)
        rows.append(row)

    if not errors and total_upper > max_budget_rub:
        errors.append(
            f"whole-matrix worst-case admission cost {total_upper:.6f} RUB exceeds ceiling {max_budget_rub:.6f} RUB"
        )

    if errors:
        write_admission_failure(
            result_path,
            max_budget_rub=max_budget_rub,
            architecture_sha=architecture_sha,
            rows=rows,
            errors=errors,
            upper_bound_rub=total_upper,
        )
        return {}, 2

    print(json.dumps({
        "admission": "PASS",
        "models": MAIN_MODELS,
        "whole_matrix_upper_bound_rub": round(total_upper, 6),
        "budget_ceiling_rub": max_budget_rub,
        "model_replacements": REPLACEMENTS,
    }, ensure_ascii=False, sort_keys=True))
    return cache, 0


pilot.MODELS = MAIN_MODELS
pilot.rub_per_token = safe_rub_per_token


if __name__ == "__main__":
    cache, rc = admission_preflight()
    if rc != 0:
        raise SystemExit(rc)

    def cached_endpoint_census(model_id: str) -> dict[str, Any]:
        try:
            return cache[model_id]
        except KeyError as exc:
            raise pilot.IntegrationError(f"model was not admitted in preflight: {model_id}") from exc

    pilot.endpoint_census = cached_endpoint_census
    raise SystemExit(pilot.main())
