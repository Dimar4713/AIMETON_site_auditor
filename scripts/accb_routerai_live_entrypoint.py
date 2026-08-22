#!/usr/bin/env python3
from __future__ import annotations

import math
from typing import Any

import accb_routerai_live_pilot as pilot


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
        if prompt_tokens > threshold:
            if key not in row:
                raise pilot.IntegrationError(
                    f"RouterAI threshold pricing omits {key}: index={index}, threshold={threshold}"
                )
            result = _positive_number(row.get(key), label=f"variable[{index}].{key}")
    return result


_original_endpoint_census = pilot.endpoint_census


def safe_endpoint_census(model_id: str) -> dict[str, Any]:
    endpoint = _original_endpoint_census(model_id)
    tag = str(endpoint.get("tag") or "").strip()
    if not tag:
        raise pilot.IntegrationError(f"RouterAI endpoint for {model_id} has no provider tag; scored call cannot be pinned")
    context_length = endpoint.get("context_length")
    if not isinstance(context_length, int) or context_length < 128_000:
        raise pilot.IntegrationError(f"invalid context_length for {model_id}: {context_length!r}")

    # Validate both low-context prices and any threshold tier reachable by this endpoint.
    safe_rub_per_token(endpoint, "prompt", 0)
    safe_rub_per_token(endpoint, "completion", 0)
    safe_rub_per_token(endpoint, "prompt", context_length)
    safe_rub_per_token(endpoint, "completion", context_length)
    return endpoint


pilot.rub_per_token = safe_rub_per_token
pilot.endpoint_census = safe_endpoint_census


if __name__ == "__main__":
    raise SystemExit(pilot.main())
