#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import accb_routerai_live_entrypoint as live
import accb_routerai_live_pilot as pilot

RETRY_MODELS = [
    "deepseek/deepseek-v4-pro-0813",
    "moonshotai/kimi-k3",
    "openai/gpt-5.6-sol",
]
PRIOR_SUCCESSFUL_MODELS = {
    "z-ai/glm-5.2": {
        "source_run": 32584584044,
        "ACI": 0.916667,
        "ACI_min": 0.5,
        "critical_failure_count": 1,
    },
    "qwen/qwen3.7-plus": {
        "source_run": 32584584044,
        "ACI": 1.0,
        "ACI_min": 1.0,
        "critical_failure_count": 0,
    },
}
SOURCE_CALIBRATION_RUN = 32584584044
RETRY_OF_RUN = 32586356270
REASONING_EFFORT = "low"
RETRY_MAX_OUTPUT_TOKENS = 8192
SAFE_WRAPPER_KEYS = ("data", "response", "result")


def _safe_shape(value: Any, depth: int = 0) -> Any:
    if depth >= 3:
        if isinstance(value, dict):
            return {"keys": sorted(str(k) for k in value.keys())}
        if isinstance(value, list):
            return {"type": "list", "length": len(value)}
        return type(value).__name__
    if isinstance(value, dict):
        out: dict[str, Any] = {"keys": sorted(str(k) for k in value.keys())}
        for key in ("data", "response", "result", "choices", "usage", "output"):
            if key in value:
                out[key] = _safe_shape(value[key], depth + 1)
        return out
    if isinstance(value, list):
        return {
            "type": "list",
            "length": len(value),
            "items": [_safe_shape(item, depth + 1) for item in value[:2]],
        }
    return type(value).__name__


def _candidate_containers(body: dict[str, Any]) -> Iterable[dict[str, Any]]:
    yield body
    for key in SAFE_WRAPPER_KEYS:
        value = body.get(key)
        if isinstance(value, dict):
            yield value
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    yield item


def _final_text_from_container(container: dict[str, Any]) -> str | None:
    top = container.get("output_text")
    if isinstance(top, str) and top.strip():
        return top.strip()

    choices = container.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    return content.strip()
                if isinstance(content, list):
                    chunks: list[str] = []
                    for part in content:
                        if not isinstance(part, dict) or part.get("type") not in {"text", "output_text"}:
                            continue
                        text = part.get("text")
                        if isinstance(text, str) and text:
                            chunks.append(text)
                    if chunks:
                        return "".join(chunks).strip()

    output = container.get("output")
    if isinstance(output, list):
        chunks: list[str] = []
        for item in output:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict) or part.get("type") not in {"text", "output_text"}:
                    continue
                text = part.get("text")
                if isinstance(text, str) and text:
                    chunks.append(text)
        if chunks:
            return "".join(chunks).strip()
    return None


def _usage_from_container(container: dict[str, Any]) -> tuple[int | None, int | None, int | None] | None:
    usage = container.get("usage")
    if not isinstance(usage, dict):
        return None

    def integer(*names: str) -> int | None:
        for name in names:
            raw = usage.get(name)
            if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 0:
                return raw
        return None

    prompt = integer("input_tokens", "prompt_tokens")
    completion = integer("output_tokens", "completion_tokens")
    total = integer("total_tokens")
    if total is None and prompt is not None and completion is not None:
        total = prompt + completion
    return prompt, completion, total


def _safe_error_summary(body: dict[str, Any]) -> dict[str, Any] | None:
    error = body.get("error")
    if not isinstance(error, dict):
        return None
    out: dict[str, Any] = {}
    for key in ("type", "code", "param", "status"):
        value = error.get(key)
        if isinstance(value, (str, int, float, bool)) or value is None:
            out[key] = value
    out["keys"] = sorted(str(k) for k in error.keys())
    return out


def _usage_summary(body: dict[str, Any]) -> dict[str, int | None]:
    for container in _candidate_containers(body):
        usage = _usage_from_container(container)
        if usage is None:
            continue
        prompt, completion, total = usage
        return {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total,
        }
    return {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None}


def _visible_text(body: dict[str, Any]) -> str | None:
    for container in _candidate_containers(body):
        text = _final_text_from_container(container)
        if text:
            return text
    return None


def _normalize_responses_body(body: dict[str, Any]) -> dict[str, Any]:
    safe_error = _safe_error_summary(body)
    usage = _usage_summary(body)
    if safe_error is not None and usage["prompt_tokens"] is None and usage["completion_tokens"] is None:
        raise pilot.IntegrationError(
            "RouterAI Responses API error before billable usage; safe_error="
            + json.dumps(safe_error, sort_keys=True, separators=(",", ":"))
        )

    text = _visible_text(body) or ""
    metadata_source: dict[str, Any] = body
    for container in _candidate_containers(body):
        if _final_text_from_container(container):
            metadata_source = container
            break

    normalized: dict[str, Any] = {
        "choices": [{"message": {"role": "assistant", "content": text}}],
        "usage": usage,
        "_routerai_transport": "responses",
        "_safe_response_shape": _safe_shape(body),
        "_retry_visible_text_present": bool(text),
    }
    if safe_error is not None:
        normalized["_safe_routerai_error"] = safe_error
    for source in (metadata_source, body):
        for key in ("model", "provider", "system_fingerprint", "id"):
            value = source.get(key)
            if key not in normalized and isinstance(value, (str, int, float)):
                normalized[key] = value
    return normalized


def _common_generation_controls(endpoint: dict[str, Any], *, live_call: bool) -> dict[str, Any]:
    if not live_call:
        return {}
    supported = endpoint.get("supported_parameters") or []
    controls: dict[str, Any] = {}
    if "reasoning" in supported:
        controls["reasoning"] = {"effort": REASONING_EFFORT}
    if "include_reasoning" in supported:
        controls["include_reasoning"] = False
    if "response_format" in supported:
        controls["response_format"] = {"type": "json_object"}
    return controls


def retry_chat(
    api_key: str,
    model_id: str,
    endpoint: dict[str, Any],
    messages: list[dict[str, str]],
    *,
    max_tokens: int,
    temperature: float = 0.0,
    timeout: int = 240,
) -> tuple[dict[str, Any], float]:
    provider_tag = str(endpoint.get("tag") or "").strip()
    if not provider_tag:
        raise pilot.IntegrationError(f"retry transport has no provider tag for {model_id}")

    transport = str(endpoint.get("api_transport") or "chat")
    live_call = max_tokens > 16
    provider = {"only": [provider_tag], "allow_fallbacks": False}
    supported = endpoint.get("supported_parameters") or []

    if transport == "chat":
        payload: dict[str, Any] = {
            "model": model_id,
            "messages": messages,
            "max_tokens": max_tokens,
            "provider": provider,
            **_common_generation_controls(endpoint, live_call=live_call),
        }
        if "temperature" in supported:
            payload["temperature"] = temperature
        _, body, elapsed = pilot.http_json(
            f"{pilot.BASE_URL}/chat/completions",
            payload=payload,
            api_key=api_key,
            timeout=timeout,
        )
        safe_error = _safe_error_summary(body)
        usage = _usage_summary(body)
        if safe_error is not None and usage["prompt_tokens"] is None and usage["completion_tokens"] is None:
            raise pilot.IntegrationError(
                "RouterAI chat API error before billable usage; safe_error="
                + json.dumps(safe_error, sort_keys=True, separators=(",", ":"))
            )
        body["_safe_response_shape"] = _safe_shape(body)
        body["_retry_visible_text_present"] = bool(_visible_text(body))
        if safe_error is not None:
            body["_safe_routerai_error"] = safe_error
        return body, elapsed

    if transport != "responses":
        raise pilot.IntegrationError(f"unsupported RouterAI retry transport: {transport!r}")

    instructions, input_messages = live._responses_input(messages)
    payload = {
        "model": model_id,
        "input": input_messages,
        "max_tokens": max_tokens,
        "provider": provider,
        **_common_generation_controls(endpoint, live_call=live_call),
    }
    if instructions:
        payload["instructions"] = instructions
    if "temperature" in supported:
        payload["temperature"] = temperature
    _, body, elapsed = pilot.http_json(
        f"{pilot.BASE_URL}/responses",
        payload=payload,
        api_key=api_key,
        timeout=timeout,
    )
    return _normalize_responses_body(body), elapsed


def retry_response_text(body: dict[str, Any]) -> str:
    text = _visible_text(body)
    if text:
        return text
    shape = json.dumps(_safe_shape(body), sort_keys=True, separators=(",", ":"))
    usage = json.dumps(_usage_summary(body), sort_keys=True, separators=(",", ":"))
    safe_error = body.get("_safe_routerai_error")
    error_suffix = ""
    if isinstance(safe_error, dict):
        error_suffix = "; safe_error=" + json.dumps(safe_error, sort_keys=True, separators=(",", ":"))
    raise pilot.IntegrationError(
        f"RouterAI result has no visible final text after usage accounting; safe_usage={usage}; safe_shape={shape}{error_suffix}"
    )


def _chat_visible_text(body: dict[str, Any]) -> str:
    return retry_response_text(body)


def _finalize_retry_metadata(result_path: Path) -> None:
    if not result_path.exists():
        return
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload["schema_version"] = "0.5-retry-accounting"
    payload["retry_of_run"] = RETRY_OF_RUN
    payload["source_calibration_run"] = SOURCE_CALIBRATION_RUN
    payload["retry_reason"] = "separate tokenizer probe from visible-answer validation and record usage/cost before live parsing"
    payload["probe_policy"] = {
        "purpose": "tokenizer/task-payload usage measurement only",
        "reasoning_controls": "disabled",
        "visible_final_text_required": False,
        "usage_required": True,
    }
    payload["reasoning_policy"] = {
        "effort": REASONING_EFFORT,
        "include_reasoning": False,
        "raw_provider_reasoning_saved": False,
    }
    payload["prior_successful_models_reused_not_repeated"] = PRIOR_SUCCESSFUL_MODELS
    payload["retry_models"] = RETRY_MODELS
    payload["accounting_policy"] = (
        "For API errors without usage, retain only sanitized error metadata; for successful envelopes with usage, "
        "account prompt/completion cost before attempting visible-final-text parsing."
    )
    for row in payload.get("rows") or []:
        if not isinstance(row, dict):
            continue
        manifest = row.get("manifest")
        endpoint = row.get("endpoint") or {}
        if isinstance(manifest, dict):
            manifest["reasoning_mode"] = REASONING_EFFORT
            manifest["max_output_tokens"] = RETRY_MAX_OUTPUT_TOKENS
            manifest["retry_of_run"] = RETRY_OF_RUN
            manifest["api_transport"] = endpoint.get("api_transport") if isinstance(endpoint, dict) else None
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    live.MAIN_MODELS = list(RETRY_MODELS)
    pilot.MODELS = list(RETRY_MODELS)
    pilot.MAX_OUTPUT_TOKENS = RETRY_MAX_OUTPUT_TOKENS
    pilot.chat = retry_chat
    pilot.response_text = retry_response_text

    cache, rc = live.admission_preflight()
    if rc != 0:
        return rc

    def cached_endpoint_census(model_id: str) -> dict[str, Any]:
        try:
            return cache[model_id]
        except KeyError as exc:
            raise pilot.IntegrationError(f"retry model was not admitted: {model_id}") from exc

    pilot.endpoint_census = cached_endpoint_census
    result_rc = pilot.main()
    result_path = Path(pilot.required_env("ACCB_RESULT_PATH"))
    live.finalize_result_transport_metadata(result_path)
    _finalize_retry_metadata(result_path)
    return result_rc


if __name__ == "__main__":
    raise SystemExit(main())
