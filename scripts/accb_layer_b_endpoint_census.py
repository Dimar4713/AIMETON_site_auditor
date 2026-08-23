#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import accb_layer_b_dry_run as dry

BASE_URL = "https://routerai.ru/api/v1"
MAX_ANCHOR_TOKENS = 524288
MAX_OUTPUT_TOKENS = 8192
TOTAL_CONTEXT_REQUIRED = MAX_ANCHOR_TOKENS + MAX_OUTPUT_TOKENS

TRANSPORT_POLICY = {
    "z-ai/glm-5.2": "chat",
    "deepseek/deepseek-v4-pro-0813": "chat",
    "qwen/qwen3.7-plus": "chat",
    "moonshotai/kimi-k3": "chat",
    "openai/gpt-5.6-sol": "responses",
}


class CensusError(RuntimeError):
    pass


def _positive_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def http_json(url: str, *, timeout: int = 60) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json",
            "User-Agent": "AIMETON-ACCB-Layer-B-Census/0.1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                raise CensusError(f"unexpected HTTP status {response.status} from {url}")
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        raise CensusError(f"read-only census failed for {url}: {exc}") from exc
    if not isinstance(body, dict):
        raise CensusError(f"read-only census returned non-object for {url}")
    return body


def endpoint_url(model_id: str) -> str:
    author, slug = model_id.split("/", 1)
    return f"{BASE_URL}/models/{author}/{slug}/endpoints"


def _endpoint_eligible(endpoint: dict[str, Any], transport: str) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    status = endpoint.get("status")
    if isinstance(status, int) and status < 0:
        reasons.append("endpoint_status_negative")

    apis = endpoint.get("supported_apis") or []
    if not isinstance(apis, list) or transport not in apis:
        reasons.append(f"transport_{transport}_not_supported")

    context_length = endpoint.get("context_length")
    if not isinstance(context_length, int) or context_length < TOTAL_CONTEXT_REQUIRED:
        reasons.append("context_length_below_532480_or_unknown")

    max_prompt = endpoint.get("max_prompt_tokens")
    if not isinstance(max_prompt, int) or max_prompt < MAX_ANCHOR_TOKENS:
        reasons.append("max_prompt_tokens_below_524288_or_unknown")

    max_completion = endpoint.get("max_completion_tokens")
    if not isinstance(max_completion, int) or max_completion < MAX_OUTPUT_TOKENS:
        reasons.append("max_completion_tokens_below_8192_or_unknown")

    tag = endpoint.get("tag")
    if not isinstance(tag, str) or not tag.strip():
        reasons.append("provider_tag_missing")

    pricing = endpoint.get("pricing")
    if not isinstance(pricing, dict):
        reasons.append("pricing_missing")
    else:
        if _positive_number(pricing.get("prompt")) is None:
            reasons.append("prompt_price_missing_or_nonpositive")
        if _positive_number(pricing.get("completion")) is None:
            reasons.append("completion_price_missing_or_nonpositive")

    return not reasons, reasons


def select_endpoint(model_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    if not isinstance(data, dict):
        raise CensusError(f"endpoint census missing data for {model_id}")
    endpoints = data.get("endpoints")
    if not isinstance(endpoints, list) or not endpoints:
        raise CensusError(f"endpoint census empty for {model_id}")

    transport = TRANSPORT_POLICY[model_id]
    rejections: list[dict[str, Any]] = []
    for index, endpoint in enumerate(endpoints):
        if not isinstance(endpoint, dict):
            continue
        eligible, reasons = _endpoint_eligible(endpoint, transport)
        if eligible:
            chosen = dict(endpoint)
            chosen["_routerai_priority_index"] = index
            chosen["_required_transport"] = transport
            chosen["_rejections_before_choice"] = rejections
            return chosen
        rejections.append(
            {
                "priority_index": index,
                "provider_name": endpoint.get("provider_name"),
                "tag": endpoint.get("tag"),
                "reasons": reasons,
            }
        )
    raise CensusError(
        f"no eligible {transport} endpoint for {model_id} with "
        f">={MAX_ANCHOR_TOKENS} prompt and >={MAX_OUTPUT_TOKENS} completion tokens; "
        f"rejections={json.dumps(rejections, ensure_ascii=False, separators=(',', ':'))}"
    )


def _rate_pair_for_prompt(endpoint: dict[str, Any], prompt_tokens: int) -> tuple[float, float, list[dict[str, Any]]]:
    pricing = endpoint.get("pricing") or {}
    base_prompt = _positive_number(pricing.get("prompt"))
    base_completion = _positive_number(pricing.get("completion"))
    if base_prompt is None or base_completion is None:
        raise CensusError("selected endpoint has invalid base pricing")

    prompt_rate = base_prompt
    completion_rate = base_completion
    applied: list[dict[str, Any]] = []
    unknown_rows: list[dict[str, Any]] = []

    for row in endpoint.get("variable_pricings") or []:
        if not isinstance(row, dict):
            continue
        row_type = row.get("type")
        row_prompt = _positive_number(row.get("prompt"))
        row_completion = _positive_number(row.get("completion"))

        if row_type == "prompt-threshold":
            threshold = row.get("threshold")
            if not isinstance(threshold, int):
                raise CensusError("prompt-threshold pricing row has no integer threshold")
            if prompt_tokens > threshold:
                if row_prompt is None or row_completion is None:
                    raise CensusError("active prompt-threshold pricing row lacks prompt/completion rates")
                prompt_rate = row_prompt
                completion_rate = row_completion
                applied.append(
                    {
                        "type": row_type,
                        "threshold": threshold,
                        "prompt": row_prompt,
                        "completion": row_completion,
                    }
                )
            continue

        # Unknown/dynamic pricing semantics are handled conservatively: if the row
        # exposes positive prompt/completion rates, reserve the maximum rate. If it
        # cannot be bounded from its own data, fail closed rather than underprice.
        if row_prompt is None and row_completion is None:
            unknown_rows.append({"type": row_type, "keys": sorted(str(k) for k in row)})
            continue
        if row_prompt is not None:
            prompt_rate = max(prompt_rate, row_prompt)
        if row_completion is not None:
            completion_rate = max(completion_rate, row_completion)
        applied.append(
            {
                "type": row_type or "unknown",
                "mode": "conservative_max_rate",
                "prompt": row_prompt,
                "completion": row_completion,
            }
        )

    if unknown_rows:
        raise CensusError(
            "selected endpoint exposes unbounded variable pricing rows: "
            + json.dumps(unknown_rows, ensure_ascii=False, separators=(",", ":"))
        )
    return prompt_rate, completion_rate, applied


def cell_cost(endpoint: dict[str, Any], prompt_tokens: int) -> dict[str, Any]:
    prompt_rate, completion_rate, applied = _rate_pair_for_prompt(endpoint, prompt_tokens)
    cost = prompt_tokens * prompt_rate + MAX_OUTPUT_TOKENS * completion_rate
    return {
        "prompt_tokens_planning_target": prompt_tokens,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "prompt_rate_rub_per_token": prompt_rate,
        "completion_rate_rub_per_token": completion_rate,
        "applied_variable_pricing": applied,
        "conservative_cost_rub": cost,
    }


def safe_endpoint_receipt(model_id: str, endpoint: dict[str, Any]) -> dict[str, Any]:
    return {
        "model_id": model_id,
        "name": endpoint.get("name"),
        "provider_name": endpoint.get("provider_name"),
        "tag": endpoint.get("tag"),
        "country": endpoint.get("country"),
        "routerai_priority_index": endpoint.get("_routerai_priority_index"),
        "required_transport": endpoint.get("_required_transport"),
        "context_length": endpoint.get("context_length"),
        "max_prompt_tokens": endpoint.get("max_prompt_tokens"),
        "max_completion_tokens": endpoint.get("max_completion_tokens"),
        "quantization": endpoint.get("quantization"),
        "supported_apis": endpoint.get("supported_apis") or [],
        "supported_parameters": endpoint.get("supported_parameters") or [],
        "pricing": endpoint.get("pricing") or {},
        "variable_pricings": endpoint.get("variable_pricings") or [],
        "seed_advertised": "seed" in (endpoint.get("supported_parameters") or []),
        "rejections_before_choice": endpoint.get("_rejections_before_choice") or [],
    }


def build_census_report(fetcher=http_json) -> dict[str, Any]:
    prereg = dry._read_json(dry.PREREG_PATH)
    if prereg.get("this_document_authorizes_spend_rub") != 0:
        raise CensusError("architecture snapshot unexpectedly authorizes spend")
    snapshot = dry.verify_snapshot()
    anchors = [int(x) for x in prereg["layer_b_diagnostic_tranche"]["anchors_tokens"]]
    if anchors != [32768, 131072, 524288]:
        raise CensusError(f"unexpected frozen Layer B anchors: {anchors}")

    selected: dict[str, Any] = {}
    cells: list[dict[str, Any]] = []
    for model_id in prereg["model_matrix"]:
        payload = fetcher(endpoint_url(model_id))
        endpoint = select_endpoint(model_id, payload)
        selected[model_id] = safe_endpoint_receipt(model_id, endpoint)
        for anchor in anchors:
            row = cell_cost(endpoint, anchor)
            row["model"] = model_id
            row["provider_tag"] = endpoint.get("tag")
            row["transport"] = TRANSPORT_POLICY[model_id]
            row["provider_pin_required"] = True
            row["allow_fallbacks"] = False
            cells.append(row)

    total = sum(float(row["conservative_cost_rub"]) for row in cells)
    return {
        "schema_version": "0.1",
        "status": "READ_ONLY_CENSUS_NO_MODEL_GENERATION",
        "source": "RouterAI public /models/{author}/{slug}/endpoints API",
        "authorization_header_sent": False,
        "routerai_generation_calls_performed": 0,
        "spend_authorized_rub": 0,
        "architecture_snapshot": snapshot,
        "capacity_gate": {
            "max_anchor_tokens": MAX_ANCHOR_TOKENS,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "total_context_required": TOTAL_CONTEXT_REQUIRED,
            "require_known_max_prompt_tokens": True,
            "require_known_max_completion_tokens": True,
        },
        "transport_policy": TRANSPORT_POLICY,
        "selected_endpoints": selected,
        "cells": cells,
        "planned_calls": len(cells),
        "whole_tranche_conservative_estimate_rub": round(total, 6),
        "logical_token_boundary": (
            "The 32K/128K/512K values remain planning targets until provider-exact "
            "tokenization is resolved; this census validates endpoint capacity/pricing, "
            "not actual L_model_input."
        ),
        "paid_execution_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only RouterAI ACCB Layer B endpoint census")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_census_report()
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
