#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import math
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_URL = "https://routerai.ru/api/v1"
ARCHITECTURE_PREREG_MERGE_SHA = "b47b937873ef980601b5c741af9b327fb18365bc"
ARCHITECTURE_NO_PAID_ASSEMBLY_MERGE_SHA = "e8bdddf17cefad5304725567c2e4270aa5990442"
MODELS = [
    "z-ai/glm-5.2",
    "deepseek/deepseek-v4-pro-0813",
    "qwen/qwen3.7-plus",
    "moonshotai/kimi-k3",
    "openai/gpt-5.6-sol",
]
ANCHORS = [32768, 131072, 524288]
MAX_OUTPUT_TOKENS = 8192
MIN_PROMPT_SUPPORT = max(ANCHORS)
SUPPORTED_APIS = ("chat", "responses")
SUPPORTED_VARIABLE_TYPES = {"prompt-threshold", "time-of-day"}


class CensusError(RuntimeError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.details = details


def _positive(raw: Any, label: str) -> float:
    if isinstance(raw, bool) or raw is None:
        raise CensusError(f"missing/invalid price: {label}={raw!r}")
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise CensusError(f"unparseable price: {label}={raw!r}") from exc
    if not math.isfinite(value) or value <= 0:
        raise CensusError(f"non-positive/non-finite price: {label}={raw!r}")
    return value


def _threshold(raw: Any, label: str) -> int:
    if isinstance(raw, bool) or raw is None:
        raise CensusError(f"missing/invalid threshold: {label}={raw!r}")
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise CensusError(f"unparseable threshold: {label}={raw!r}") from exc
    if not math.isfinite(value) or value < 0 or not value.is_integer():
        raise CensusError(f"invalid threshold: {label}={raw!r}")
    return int(value)


def get_json(url: str, timeout: int = 60) -> dict[str, Any]:
    if not url.startswith(BASE_URL + "/models/") or not url.endswith("/endpoints"):
        raise CensusError(f"GET-only census refuses URL outside model endpoints: {url}")
    req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw_bytes = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read()
        raise CensusError(
            f"endpoint GET failed: HTTP {exc.code}; body_bytes={len(detail)}; "
            f"body_sha256={hashlib.sha256(detail).hexdigest()}"
        ) from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None)
        raise CensusError(
            f"endpoint GET transport failure: reason_type={type(reason).__name__}"
        ) from exc

    raw = raw_bytes.decode("utf-8", errors="replace")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CensusError(
            f"endpoint GET returned invalid JSON: body_bytes={len(raw_bytes)}; "
            f"body_sha256={hashlib.sha256(raw_bytes).hexdigest()}"
        ) from exc
    if not isinstance(value, dict):
        raise CensusError("endpoint GET returned non-object JSON")
    return value


def _transport(apis: Any) -> str | None:
    if not isinstance(apis, list):
        return None
    for candidate in SUPPORTED_APIS:
        if candidate in apis:
            return candidate
    return None


def _capacity_rejection_reasons(endpoint: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    required_context = MIN_PROMPT_SUPPORT + MAX_OUTPUT_TOKENS
    context = endpoint.get("context_length")
    if not isinstance(context, int):
        reasons.append("context_length_missing_or_non_integer")
    elif context < required_context:
        reasons.append("context_length_below_prompt_plus_output_reserve")
    max_prompt = endpoint.get("max_prompt_tokens")
    if isinstance(max_prompt, int) and max_prompt < MIN_PROMPT_SUPPORT:
        reasons.append("max_prompt_tokens_below_524288")
    max_completion = endpoint.get("max_completion_tokens")
    if isinstance(max_completion, int) and max_completion < MAX_OUTPUT_TOKENS:
        reasons.append("max_completion_tokens_below_8192")
    return reasons


def _supports_anchor(endpoint: dict[str, Any], anchor: int) -> bool:
    context = endpoint.get("context_length")
    if not isinstance(context, int) or context < anchor + MAX_OUTPUT_TOKENS:
        return False
    max_prompt = endpoint.get("max_prompt_tokens")
    if isinstance(max_prompt, int) and max_prompt < anchor:
        return False
    max_completion = endpoint.get("max_completion_tokens")
    if isinstance(max_completion, int) and max_completion < MAX_OUTPUT_TOKENS:
        return False
    return True


def _safe_endpoint_observation(endpoint: dict[str, Any]) -> dict[str, Any]:
    apis = endpoint.get("supported_apis")
    params = endpoint.get("supported_parameters")
    pricing = endpoint.get("pricing")
    variable = endpoint.get("variable_pricings")
    variable_types: list[str] = []
    if isinstance(variable, list):
        variable_types = sorted(
            str(row.get("type"))
            for row in variable
            if isinstance(row, dict) and row.get("type") is not None
        )[:16]
    return {
        "provider_name": str(endpoint.get("provider_name") or "")[:120],
        "tag": str(endpoint.get("tag") or "")[:120],
        "status": endpoint.get("status") if isinstance(endpoint.get("status"), (int, str)) else None,
        "context_length": endpoint.get("context_length") if isinstance(endpoint.get("context_length"), int) else None,
        "max_prompt_tokens": endpoint.get("max_prompt_tokens") if isinstance(endpoint.get("max_prompt_tokens"), int) else None,
        "max_completion_tokens": endpoint.get("max_completion_tokens") if isinstance(endpoint.get("max_completion_tokens"), int) else None,
        "supported_apis": sorted(str(x) for x in apis if isinstance(x, str))[:16] if isinstance(apis, list) else [],
        "supported_parameters": sorted(str(x) for x in params if isinstance(x, str))[:64] if isinstance(params, list) else [],
        "pricing_object_present": isinstance(pricing, dict),
        "prompt_price_present": isinstance(pricing, dict) and "prompt" in pricing,
        "completion_price_present": isinstance(pricing, dict) and "completion" in pricing,
        "variable_pricing_types": variable_types,
    }


def _sanitize_variable_rows(rows: Any) -> list[dict[str, Any]]:
    if rows is None:
        return []
    if not isinstance(rows, list):
        raise CensusError("variable_pricings is not a list")
    safe: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise CensusError(f"variable pricing row {index} is not an object")
        kind = row.get("type")
        if kind not in SUPPORTED_VARIABLE_TYPES:
            raise CensusError(f"unsupported variable pricing type: {kind!r}")
        item: dict[str, Any] = {"type": kind}
        if kind == "prompt-threshold":
            item["threshold"] = _threshold(row.get("threshold"), f"variable[{index}].threshold")
        if kind == "time-of-day":
            item["utc_start"] = row.get("utc_start")
            item["utc_end"] = row.get("utc_end")
        for key in ("prompt", "completion"):
            if key in row:
                item[key] = _positive(row.get(key), f"variable[{index}].{key}")
        if "prompt" not in item and "completion" not in item:
            raise CensusError(f"variable pricing row {index} has no prompt/completion price")
        safe.append(item)
    return safe


def select_endpoint(model: str, body: dict[str, Any]) -> dict[str, Any]:
    data = body.get("data")
    endpoints = data.get("endpoints") if isinstance(data, dict) else None
    if not isinstance(endpoints, list) or not endpoints:
        raise CensusError(f"no endpoint data for {model}")
    candidates: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    for endpoint in endpoints:
        if not isinstance(endpoint, dict):
            continue
        observation = _safe_endpoint_observation(endpoint)
        reasons: list[str] = []
        tag = str(endpoint.get("tag") or "").strip()
        transport = _transport(endpoint.get("supported_apis"))
        status = endpoint.get("status")
        if not tag:
            reasons.append("provider_tag_missing")
        if transport is None:
            reasons.append("supported_chat_or_responses_transport_missing")
        if isinstance(status, int) and status < 0:
            reasons.append("endpoint_status_negative")
        reasons.extend(_capacity_rejection_reasons(endpoint))
        pricing = endpoint.get("pricing")
        if not isinstance(pricing, dict):
            reasons.append("pricing_object_missing")
        observation["selected_transport_if_eligible"] = transport
        observation["rejection_reasons"] = reasons
        observations.append(observation)
        if reasons:
            continue

        try:
            prompt = _positive(pricing.get("prompt"), f"{model}.{tag}.base.prompt")
            completion = _positive(pricing.get("completion"), f"{model}.{tag}.base.completion")
            variable = _sanitize_variable_rows(endpoint.get("variable_pricings") or [])
        except CensusError as exc:
            observation["rejection_reasons"] = ["pricing_contract_invalid"]
            raise CensusError(
                str(exc),
                details={
                    "model": model,
                    "required_prompt_tokens": MIN_PROMPT_SUPPORT,
                    "required_output_reserve_tokens": MAX_OUTPUT_TOKENS,
                    "observed_endpoints": observations[:16],
                },
            ) from exc
        candidates.append({
            "model": model,
            "provider_name": str(endpoint.get("provider_name") or ""),
            "tag": tag,
            "transport": transport,
            "status": status,
            "context_length": endpoint.get("context_length"),
            "max_prompt_tokens": endpoint.get("max_prompt_tokens"),
            "max_completion_tokens": endpoint.get("max_completion_tokens"),
            "supported_parameters": sorted(str(x) for x in (endpoint.get("supported_parameters") or [])),
            "supported_apis": endpoint.get("supported_apis") or [],
            "pricing": {"prompt": prompt, "completion": completion},
            "variable_pricings": variable,
        })
    if not candidates:
        raise CensusError(
            f"no healthy priced endpoint supports all Layer B anchors for {model}",
            details={
                "model": model,
                "required_prompt_tokens": MIN_PROMPT_SUPPORT,
                "required_output_reserve_tokens": MAX_OUTPUT_TOKENS,
                "observed_endpoints": observations[:16],
            },
        )
    return candidates[0]


def conservative_rates(endpoint: dict[str, Any], anchor: int) -> tuple[float, float, list[str]]:
    prompt = _positive((endpoint.get("pricing") or {}).get("prompt"), "base.prompt")
    completion = _positive((endpoint.get("pricing") or {}).get("completion"), "base.completion")
    applied = ["base"]
    for row in endpoint.get("variable_pricings") or []:
        kind = row.get("type")
        eligible = kind == "time-of-day"
        if kind == "prompt-threshold":
            eligible = anchor > int(row["threshold"])
        if not eligible:
            continue
        row_used = False
        if "prompt" in row:
            prompt = max(prompt, _positive(row["prompt"], f"{kind}.prompt"))
            row_used = True
        if "completion" in row:
            completion = max(completion, _positive(row["completion"], f"{kind}.completion"))
            row_used = True
        if row_used:
            applied.append(kind)
    return prompt, completion, applied


def price_endpoint(endpoint: dict[str, Any]) -> dict[str, Any]:
    rows: dict[str, Any] = {}
    total = 0.0
    for anchor in ANCHORS:
        prompt_rate, completion_rate, applied = conservative_rates(endpoint, anchor)
        cost = anchor * prompt_rate + MAX_OUTPUT_TOKENS * completion_rate
        rows[str(anchor)] = {
            "prompt_rate_rub_per_token": prompt_rate,
            "completion_rate_rub_per_token": completion_rate,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "applied_pricing_classes": applied,
            "estimated_cost_rub": round(cost, 6),
        }
        total += cost
    return {"anchors": rows, "model_total_rub": round(total, 6)}


def _base_receipt(status: str) -> dict[str, Any]:
    return {
        "schema_version": "0.3-endpoint-rejection-observable",
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "site_auditor_sha": os.getenv("GITHUB_SHA"),
        "architecture_prereg_merge_sha": ARCHITECTURE_PREREG_MERGE_SHA,
        "architecture_no_paid_assembly_merge_sha": ARCHITECTURE_NO_PAID_ASSEMBLY_MERGE_SHA,
        "models": [],
        "anchors_tokens_nominal": ANCHORS,
        "max_output_tokens_per_cell": MAX_OUTPUT_TOKENS,
        "planned_cells": len(MODELS) * len(ANCHORS),
        "whole_tranche_conservative_estimate_rub": None,
        "pricing_policy": "prompt-threshold only above threshold; highest advertised time-of-day rate; no cache discount; unknown variable pricing fails closed",
        "http_methods": ["GET"],
        "routerai_authorization_header_sent": False,
        "provider_generations_performed": 0,
        "paid_spend_authorized_rub": 0,
        "scientific_boundary": "Pricing/capability admission evidence only; no cognition score or ECC/AMCE threshold inference.",
    }


def census(fetcher=get_json) -> dict[str, Any]:
    model_rows: list[dict[str, Any]] = []
    total = 0.0
    for model in MODELS:
        author, slug = model.split("/", 1)
        url = f"{BASE_URL}/models/{author}/{slug}/endpoints"
        body = fetcher(url)
        endpoint = select_endpoint(model, body)
        estimate = price_endpoint(endpoint)
        total += float(estimate["model_total_rub"])
        model_rows.append({
            **endpoint,
            "seed_advertised_fresh": "seed" in endpoint["supported_parameters"],
            "estimate": estimate,
        })
    result = _base_receipt("FRESH_READ_ONLY_CENSUS")
    result["models"] = model_rows
    result["whole_tranche_conservative_estimate_rub"] = round(total, 6)
    return result


def failure_receipt(exc: BaseException) -> dict[str, Any]:
    result = _base_receipt("FRESH_READ_ONLY_CENSUS_FAILED")
    if isinstance(exc, CensusError):
        result["failure"] = {
            "error_type": type(exc).__name__,
            "safe_message": str(exc)[:1000],
        }
        if isinstance(exc.details, dict):
            result["failure"]["safe_details"] = exc.details
    else:
        raw = repr(exc).encode("utf-8", errors="replace")
        result["failure"] = {
            "error_type": type(exc).__name__,
            "safe_message": "unexpected internal census failure; raw exception not retained",
            "exception_repr_bytes": len(raw),
            "exception_repr_sha256": hashlib.sha256(raw).hexdigest(),
        }
    return result


def _write_result(result: dict[str, Any], output: Path | None) -> None:
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    print(text, end="")


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = census()
        rc = 0
    except BaseException as exc:
        result = failure_receipt(exc)
        rc = 2
    _write_result(result, args.output)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
