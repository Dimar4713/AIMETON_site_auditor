#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import accb_routerai_live_entrypoint as live
import accb_routerai_live_pilot as pilot
import accb_routerai_retry_v2_entrypoint as _impl

# Historical three-model retry exports remain compatible. The v2 implementation
# is frozen; Sol-specific transport hardening is isolated below.
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
SOL_PREVIOUS_USAGELESS_RUN = 32618857912
SOL_MAX_OUTPUT_TOKENS = RETRY_MAX_OUTPUT_TOKENS
SOL_RESPONSES_OUTPUT_LIMIT_KEY = "max_output_tokens"
SOL_RESPONSES_STRUCTURED_OUTPUT_KEY = "text.format"
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
_SOL_LIVE_RECEIPT: dict[str, Any] | None = None
_SOL_ERROR_RECEIPT: dict[str, Any] | None = None
_SOL_USAGE_PATHS: dict[str, str | None] = {"probe": None, "live": None}
_SOL_MISSING_USAGE_DIAGNOSTIC: dict[str, Any] | None = None
_SOL_SAFE_ERROR_DIAGNOSTIC: dict[str, Any] | None = None

_TOKEN_KEYS = {
    "input_tokens",
    "prompt_tokens",
    "output_tokens",
    "completion_tokens",
    "total_tokens",
    "input_token_count",
    "output_token_count",
    "prompt_token_count",
    "completion_token_count",
    "cost",
}
_ID_KEYS = {"id", "request_id", "response_id", "generation_id"}
_SAFE_ERROR_MARKERS = (
    "invalid_request",
    "bad_request",
    "unsupported_parameter",
    "unsupported",
    "input",
    "instructions",
    "max_tokens",
    "max_output_tokens",
    "response_format",
    "text",
    "format",
    "structured_outputs",
    "provider",
    "model",
    "authentication",
    "unauthorized",
    "forbidden",
    "rate_limit",
    "capacity",
    "timeout",
    "reasoning",
    "include_reasoning",
    "temperature",
    "tool_choice",
    "tools",
)


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
    env_path = os.getenv("GITHUB_ENV", "").strip()
    if not env_path:
        return
    with open(env_path, "a", encoding="utf-8") as handle:
        handle.write("ACCB_EXPECTED_MODELS=1\n")
        handle.write(f"ACCB_EVIDENCE_LABEL={SOL_EVIDENCE_LABEL}\n")


def _integer(mapping: dict[str, Any], *names: str) -> int | None:
    for name in names:
        raw = mapping.get(name)
        if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 0:
            return raw
    return None


def _usage_tuple(mapping: dict[str, Any]) -> tuple[int | None, int | None, int | None]:
    prompt = _integer(mapping, "input_tokens", "prompt_tokens", "input_token_count", "prompt_token_count")
    completion = _integer(
        mapping,
        "output_tokens",
        "completion_tokens",
        "output_token_count",
        "completion_token_count",
    )
    total = _integer(mapping, "total_tokens")
    if total is None and prompt is not None and completion is not None:
        total = prompt + completion
    return prompt, completion, total


def _walk_objects(value: Any, path: str = "$"):
    if isinstance(value, dict):
        yield path, value
        for key, child in value.items():
            if isinstance(child, (dict, list)):
                yield from _walk_objects(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            if isinstance(child, (dict, list)):
                yield from _walk_objects(child, f"{path}[{index}]")


def _recursive_usage(body: dict[str, Any]) -> tuple[int | None, int | None, int | None, str | None]:
    """Find Responses usage without assuming RouterAI's wrapper depth."""
    candidates = list(_walk_objects(body))
    candidates.sort(key=lambda item: (0 if item[0].endswith(".usage") else 1, item[0].count("."), item[0]))
    for path, mapping in candidates:
        prompt, completion, total = _usage_tuple(mapping)
        if prompt is not None and completion is not None:
            return prompt, completion, total, path
    return None, None, None, None


def _safe_usage_diagnostic(body: dict[str, Any]) -> dict[str, Any]:
    """Retain structure needed to repair accounting, never prompt/output text."""
    objects: list[dict[str, Any]] = []
    ids: list[dict[str, str]] = []
    for path, mapping in _walk_objects(body):
        keys = sorted(str(key) for key in mapping.keys())
        interesting = sorted(
            key for key in keys
            if key in _TOKEN_KEYS or key in _ID_KEYS or key in {"usage", "meta", "billing"}
        )
        if interesting:
            objects.append({"path": path, "keys": keys[:80], "interesting_keys": interesting})
        for key in _ID_KEYS:
            value = mapping.get(key)
            if isinstance(value, str) and value and len(ids) < 8:
                ids.append({"path": f"{path}.{key}", "value": value[:200]})
    return {
        "top_level_keys": sorted(str(key) for key in body.keys())[:100],
        "usage_related_objects": objects[:24],
        "request_ids": ids,
    }


def _classify_error_text(text: str) -> dict[str, Any]:
    """Fingerprint provider error text without retaining the text itself."""
    lowered = text.lower()
    return {
        "error_text_length": len(text),
        "error_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "safe_markers": [marker for marker in _SAFE_ERROR_MARKERS if marker in lowered],
    }


def _safe_error_descriptor(body: dict[str, Any], *, http_status: int) -> dict[str, Any] | None:
    """Sanitize a non-null RouterAI `error` envelope.

    RouterAI Responses success envelopes may include the nullable sentinel
    `"error": null`; that is explicitly absence of an API error and must not
    block an otherwise accounted probe. Non-null errors remain fail-closed.
    Arbitrary provider message text is never retained.
    """
    if "error" not in body:
        return None
    error = body.get("error")
    if error is None:
        return None
    descriptor: dict[str, Any] = {
        "http_status": http_status,
        "error_value_type": type(error).__name__,
    }
    if isinstance(error, dict):
        base = _impl._safe_error_summary(body) or {}
        descriptor.update(base)
        message = error.get("message")
        if isinstance(message, str):
            descriptor.update(_classify_error_text(message))
        return descriptor
    if isinstance(error, str):
        descriptor.update(_classify_error_text(error))
        return descriptor
    if isinstance(error, list):
        descriptor["error_list_length"] = len(error)
        descriptor["error_item_types"] = sorted({type(item).__name__ for item in error})[:16]
        return descriptor
    if isinstance(error, (int, float, bool)):
        return descriptor
    descriptor["error_repr_sha256"] = hashlib.sha256(repr(error).encode("utf-8")).hexdigest()
    return descriptor


def _metadata_from_raw(body: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for _, mapping in _walk_objects(body):
        for key in ("model", "provider", "system_fingerprint", "id"):
            value = mapping.get(key)
            if key not in result and isinstance(value, (str, int, float)):
                result[key] = value
        if len(result) >= 4:
            break
    return result


def _normalize_sol_responses(raw: dict[str, Any], *, live_call: bool) -> dict[str, Any]:
    global _SOL_MISSING_USAGE_DIAGNOSTIC
    prompt, completion, total, usage_path = _recursive_usage(raw)
    diagnostic = _safe_usage_diagnostic(raw)
    phase = "live" if live_call else "probe"
    _SOL_USAGE_PATHS[phase] = usage_path

    text = _impl._visible_text(raw) or ""
    normalized: dict[str, Any] = {
        "choices": [{"message": {"role": "assistant", "content": text}}],
        "usage": {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total,
        },
        "_routerai_transport": "responses",
        "_sol_usage_path": usage_path,
        "_sol_usage_diagnostic": diagnostic,
        "_retry_visible_text_present": bool(text),
    }
    normalized.update(_metadata_from_raw(raw))
    if prompt is None or completion is None:
        normalized["_sol_usage_missing"] = True
        normalized["_sol_usage_missing_phase"] = phase
        _SOL_MISSING_USAGE_DIAGNOSTIC = {"phase": phase, **diagnostic}
    return normalized


def _sol_responses_generation_controls(endpoint: dict[str, Any], *, live_call: bool) -> dict[str, Any]:
    """Translate shared Chat/proxy controls to the provider-native Responses wire contract."""
    controls = dict(_impl._common_generation_controls(endpoint, live_call=live_call))
    # RouterAI advertises include_reasoning as a generic model control, but the
    # native OpenAI Responses request contract uses `reasoning` and has no
    # top-level `include_reasoning` request field. Never forward that proxy key.
    controls.pop("include_reasoning", None)
    response_format = controls.pop("response_format", None)
    if response_format is not None:
        controls["text"] = {"format": response_format}
    return controls


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
    """Responses transport with safe error classification and pre-live accounting gate."""
    global _SOL_ERROR_RECEIPT, _SOL_LIVE_RECEIPT, _SOL_SAFE_ERROR_DIAGNOSTIC

    if str(endpoint.get("api_transport") or "") != "responses":
        return _impl.retry_chat(
            api_key,
            model_id,
            endpoint,
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
        )

    provider_tag = str(endpoint.get("tag") or "").strip()
    if not provider_tag:
        raise pilot.IntegrationError(f"Sol Responses transport has no provider tag for {model_id}")
    live_call = max_tokens > 16
    phase = "live" if live_call else "probe"
    instructions, input_messages = live._responses_input(messages)
    payload: dict[str, Any] = {
        "model": model_id,
        "input": input_messages,
        SOL_RESPONSES_OUTPUT_LIMIT_KEY: max_tokens,
        "provider": {"only": [provider_tag], "allow_fallbacks": False},
        **_sol_responses_generation_controls(endpoint, live_call=live_call),
    }
    if instructions:
        payload["instructions"] = instructions
    supported = endpoint.get("supported_parameters") or []
    if "temperature" in supported:
        payload["temperature"] = temperature

    http_status, raw, elapsed = pilot.http_json(
        f"{pilot.BASE_URL}/responses",
        payload=payload,
        api_key=api_key,
        timeout=timeout,
    )
    prompt, completion, total, usage_path = _recursive_usage(raw)
    safe_error = _safe_error_descriptor(raw, http_status=http_status)
    if safe_error is not None:
        structure = _safe_usage_diagnostic(raw)
        _SOL_USAGE_PATHS[phase] = usage_path
        _SOL_SAFE_ERROR_DIAGNOSTIC = {
            "phase": phase,
            "safe_error": safe_error,
            "usage_path": usage_path,
            "structure": structure,
        }
        if isinstance(prompt, int) and isinstance(completion, int):
            if not isinstance(total, int):
                total = prompt + completion
            _SOL_ERROR_RECEIPT = {
                "usage": {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": total},
                "usage_path": usage_path,
                "estimated_cost_rub": round(pilot.estimated_cost(endpoint, prompt, completion), 6),
                "elapsed_seconds": round(elapsed, 6),
            }
        compact = json.dumps(safe_error, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        raise pilot.IntegrationError(
            f"RouterAI Responses returned sanitized API error envelope; safe_error={compact[:760]}"
        )

    body = _normalize_sol_responses(raw, live_call=live_call)
    summary = _impl._usage_summary(body)
    prompt = summary.get("prompt_tokens")
    completion = summary.get("completion_tokens")
    if live_call and isinstance(prompt, int) and isinstance(completion, int):
        total = summary.get("total_tokens")
        if not isinstance(total, int):
            total = prompt + completion
        _SOL_LIVE_RECEIPT = {
            "usage": {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": total},
            "usage_path": body.get("_sol_usage_path"),
            "estimated_cost_rub": round(pilot.estimated_cost(endpoint, prompt, completion), 6),
            "elapsed_seconds": round(elapsed, 6),
            "provider_metadata": pilot.safe_provider_metadata(body),
        }
    return body, elapsed


def _sol_usage(body: dict[str, Any]) -> tuple[int | None, int | None, int | None]:
    prompt, completion, total = _ORIGINAL_USAGE(body)
    if body.get("_sol_usage_missing") is True and (prompt is None or completion is None):
        phase = str(body.get("_sol_usage_missing_phase") or "unknown")
        diagnostic = body.get("_sol_usage_diagnostic")
        compact = json.dumps(diagnostic, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        raise pilot.IntegrationError(
            f"Sol Responses {phase} returned no discoverable token usage; safe_usage_structure={compact[:760]}"
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
        if isinstance(probe, dict):
            probe_cost = probe.get("estimated_cost_rub")
            if isinstance(probe_cost, (int, float)) and not isinstance(probe_cost, bool):
                known += float(probe_cost)
    return known


def _finalize_sol_metadata(result_path: Path) -> None:
    if not result_path.exists():
        return
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload["schema_version"] = "1.2-sol-native-reasoning-contract"
    payload["retry_scope"] = "sol-only"
    payload["retry_of_run"] = SOL_PREVIOUS_USAGELESS_RUN
    payload["source_calibration_runs"] = [32584584044, SOL_SOURCE_RUN]
    payload["prior_successful_models_reused_not_repeated"] = FOUR_MODEL_EVIDENCE
    payload["retry_models"] = list(SOL_RETRY_MODELS)
    payload["responses_request_adapter"] = {
        "output_limit_key": SOL_RESPONSES_OUTPUT_LIMIT_KEY,
        "structured_output_key": SOL_RESPONSES_STRUCTURED_OUTPUT_KEY,
        "reasoning_key": "reasoning.effort",
        "include_reasoning_top_level_omitted": True,
        "routerai_catalog_declared_output_limit_key": "max_tokens",
        "routerai_catalog_declared_structured_output_key": "response_format",
        "provider_native_contract": "OpenAI Responses API max_output_tokens + text.format + reasoning.effort; no top-level include_reasoning",
        "provider_pin_preserved": True,
        "null_error_semantics": "error:null is a no-error sentinel; only non-null error values are fail-closed",
    }
    payload["responses_usage_discovery"] = {
        "strategy": "recursive numeric token-counter search across the RouterAI Responses envelope",
        "probe_usage_path": _SOL_USAGE_PATHS.get("probe"),
        "live_usage_path": _SOL_USAGE_PATHS.get("live"),
        "raw_text_or_reasoning_retained": False,
    }
    payload["error_envelope_policy"] = {
        "arbitrary_error_text_retained": False,
        "null_error_is_error": False,
        "non_null_error_is_fail_closed": True,
        "retained": "HTTP status, error value type, allowlisted type/code/param/status, hash/length and allowlisted markers",
        "full_benchmark_after_error": False,
    }
    payload["probe_policy"] = {
        "purpose": "tiny transport/accounting capability gate before the full Sol benchmark request",
        "visible_final_text_required": False,
        "usage_required_before_live_call": True,
        "failure_behavior": "stop before the 80K-class benchmark call on non-null API error or missing exact usage",
    }
    payload["accounting_policy"] = (
        "No synthetic token counts are accepted. A non-null error envelope stops the run before the full Sol request. "
        "A nullable error:null sentinel does not override otherwise valid exact usage."
    )

    if _SOL_SAFE_ERROR_DIAGNOSTIC is not None:
        payload["safe_error_diagnostic"] = _SOL_SAFE_ERROR_DIAGNOSTIC
        if _SOL_ERROR_RECEIPT is None:
            payload["current_run_spend_status"] = "UNKNOWN/unreconciled: RouterAI error envelope exposed no token usage"
            payload["estimated_spend_rub"] = None
        else:
            payload["current_run_spend_status"] = "CONFIRMED/accounted from error-envelope usage"
            payload["estimated_spend_rub"] = _SOL_ERROR_RECEIPT["estimated_cost_rub"]
    elif _SOL_MISSING_USAGE_DIAGNOSTIC is not None:
        payload["current_run_spend_status"] = "UNKNOWN/unreconciled: non-error Responses envelope omitted discoverable token usage"
        payload["estimated_spend_rub"] = None
        payload["safe_usage_diagnostic"] = _SOL_MISSING_USAGE_DIAGNOSTIC

    for row in payload.get("rows") or []:
        if not isinstance(row, dict) or row.get("model_identifier") != SOL_MODEL:
            continue
        endpoint = row.get("endpoint") if isinstance(row.get("endpoint"), dict) else {}
        if _SOL_SAFE_ERROR_DIAGNOSTIC is not None:
            row["safe_error_diagnostic"] = _SOL_SAFE_ERROR_DIAGNOSTIC
            if _SOL_ERROR_RECEIPT is None:
                row["usage_accounting_status"] = "UNKNOWN/unreconciled"
            else:
                row["usage"] = dict(_SOL_ERROR_RECEIPT["usage"])
                row["estimated_cost_rub"] = _SOL_ERROR_RECEIPT["estimated_cost_rub"]
                row["usage_accounting_status"] = "CONFIRMED/accounted"
                row["usage_path"] = _SOL_ERROR_RECEIPT.get("usage_path")
        elif _SOL_MISSING_USAGE_DIAGNOSTIC is not None:
            row["usage_accounting_status"] = "UNKNOWN/unreconciled"
            row["safe_usage_diagnostic"] = _SOL_MISSING_USAGE_DIAGNOSTIC

        if _SOL_LIVE_RECEIPT is not None:
            if not isinstance(row.get("usage"), dict):
                row["usage"] = dict(_SOL_LIVE_RECEIPT["usage"])
            if not isinstance(row.get("estimated_cost_rub"), (int, float)):
                row["estimated_cost_rub"] = _SOL_LIVE_RECEIPT["estimated_cost_rub"]
            row.setdefault("elapsed_seconds", _SOL_LIVE_RECEIPT["elapsed_seconds"])
            row.setdefault("provider_metadata", _SOL_LIVE_RECEIPT["provider_metadata"])
            row["usage_accounted_before_candidate_parse"] = True
            row["usage_path"] = _SOL_LIVE_RECEIPT.get("usage_path")

        manifest = row.get("manifest")
        if isinstance(manifest, dict):
            manifest["reasoning_mode"] = REASONING_EFFORT
            manifest["max_output_tokens"] = SOL_MAX_OUTPUT_TOKENS
            manifest["retry_of_run"] = SOL_PREVIOUS_USAGELESS_RUN
            manifest["api_transport"] = endpoint.get("api_transport")
            manifest["responses_output_limit_key"] = SOL_RESPONSES_OUTPUT_LIMIT_KEY
            manifest["responses_structured_output_key"] = SOL_RESPONSES_STRUCTURED_OUTPUT_KEY
            manifest["responses_include_reasoning_sent"] = False
            manifest["responses_null_error_is_error"] = False

    known = _known_cost_from_payload(payload)
    if _SOL_ERROR_RECEIPT is not None and not known:
        known = float(_SOL_ERROR_RECEIPT["estimated_cost_rub"])
    payload["confirmed_accounted_spend_rub"] = round(known, 6) if known else 0.0
    payload["scientific_claim_boundary"] = (
        "Fifth-model low-context calibration/integration evidence only; no universal ECC/AMCE threshold inference."
    )
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sol_main() -> int:
    global _SOL_ERROR_RECEIPT, _SOL_LIVE_RECEIPT, _SOL_MISSING_USAGE_DIAGNOSTIC, _SOL_SAFE_ERROR_DIAGNOSTIC
    _SOL_LIVE_RECEIPT = None
    _SOL_ERROR_RECEIPT = None
    _SOL_MISSING_USAGE_DIAGNOSTIC = None
    _SOL_SAFE_ERROR_DIAGNOSTIC = None
    _SOL_USAGE_PATHS["probe"] = None
    _SOL_USAGE_PATHS["live"] = None
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