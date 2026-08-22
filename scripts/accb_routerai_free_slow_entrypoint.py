#!/usr/bin/env python3
from __future__ import annotations

import math
from typing import Any

import accb_routerai_live_pilot as pilot

FREE_MODEL = "stealth/ox-alpha"


def _number(raw: Any, *, label: str) -> float:
    if isinstance(raw, bool) or raw is None:
        raise pilot.IntegrationError(f"missing/invalid RouterAI price: {label}={raw!r}")
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise pilot.IntegrationError(f"unparseable RouterAI price: {label}={raw!r}") from exc
    if not math.isfinite(value) or value < 0:
        raise pilot.IntegrationError(f"negative/non-finite RouterAI price: {label}={raw!r}")
    return value


def free_rub_per_token(endpoint: dict[str, Any], key: str, prompt_tokens: int) -> float:
    if endpoint.get("model_id") != FREE_MODEL:
        raise pilot.IntegrationError("free pricing override attempted for a non-allowlisted model")
    pricing = endpoint.get("pricing")
    if not isinstance(pricing, dict):
        raise pilot.IntegrationError("RouterAI endpoint has no pricing object")
    base = _number(pricing.get(key), label=f"base.{key}")
    if base != 0.0:
        raise pilot.IntegrationError(f"{FREE_MODEL} is no longer free for {key}: {base}")
    variable = endpoint.get("variable_pricings") or []
    if variable:
        for index, row in enumerate(variable):
            if not isinstance(row, dict):
                raise pilot.IntegrationError(f"invalid variable pricing row: {index}")
            if row.get("type") == "prompt-threshold":
                for price_key in ("prompt", "completion"):
                    if price_key in row and _number(row[price_key], label=f"variable[{index}].{price_key}") != 0.0:
                        raise pilot.IntegrationError(f"{FREE_MODEL} has a non-zero threshold price")
    return 0.0


_original_endpoint_census = pilot.endpoint_census
_original_chat = pilot.chat


def free_endpoint_census(model_id: str) -> dict[str, Any]:
    if model_id != FREE_MODEL:
        raise pilot.IntegrationError(f"unexpected model in free lane: {model_id}")
    endpoint = _original_endpoint_census(model_id)
    tag = str(endpoint.get("tag") or "").strip()
    if not tag:
        raise pilot.IntegrationError(f"RouterAI endpoint for {model_id} has no provider tag")
    context_length = endpoint.get("context_length")
    if not isinstance(context_length, int) or context_length < 512_000:
        raise pilot.IntegrationError(f"free long-context lane requires >=512K context, got {context_length!r}")
    free_rub_per_token(endpoint, "prompt", 0)
    free_rub_per_token(endpoint, "completion", 0)
    free_rub_per_token(endpoint, "prompt", context_length)
    free_rub_per_token(endpoint, "completion", context_length)
    return endpoint


def slow_chat(api_key: str, model_id: str, endpoint: dict[str, Any], messages: list[dict[str, str]], *, max_tokens: int, temperature: float = 0.0, timeout: int = 240):
    # ox-alpha is intentionally isolated because preview/free capacity can be slow.
    return _original_chat(
        api_key,
        model_id,
        endpoint,
        messages,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout=max(timeout, 1200),
    )


pilot.MODELS = [FREE_MODEL]
pilot.rub_per_token = free_rub_per_token
pilot.endpoint_census = free_endpoint_census
pilot.chat = slow_chat


if __name__ == "__main__":
    raise SystemExit(pilot.main())
