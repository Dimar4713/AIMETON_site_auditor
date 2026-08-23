#!/usr/bin/env python3
from __future__ import annotations

import hashlib
from typing import Any, Callable

ARCHITECTURE_NO_PAID_MERGE_SHA = "e8bdddf17cefad5304725567c2e4270aa5990442"
FROZEN_ANCHORS = (32768, 131072, 524288)


class ContractError(RuntimeError):
    pass


def _require_uint32(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 0xFFFFFFFF:
        raise ContractError("seed must be an unsigned 32-bit integer")
    return value


def provider_seed_decision(
    *,
    seed_value: int,
    supported_parameters: list[str] | tuple[str, ...],
    fresh_endpoint_seed_advertised: bool | None,
    transport_contract_status: str,
    validated_wire_key: str | None,
) -> dict[str, Any]:
    """Fail-closed provider seed admission. This function performs no I/O."""
    seed = _require_uint32(seed_value)
    supported = {str(item) for item in supported_parameters}
    fresh_support = fresh_endpoint_seed_advertised is True and "seed" in supported
    transport_pass = transport_contract_status == "PASS" and validated_wire_key == "seed"
    authorized = fresh_support and transport_pass
    reasons: list[str] = []
    if fresh_endpoint_seed_advertised is not True:
        reasons.append("fresh endpoint seed capability is not confirmed")
    if "seed" not in supported:
        reasons.append("selected endpoint supported_parameters does not advertise seed")
    if transport_contract_status != "PASS":
        reasons.append("transport seed contract is not PASS")
    if validated_wire_key != "seed":
        reasons.append("validated wire key is not exact top-level seed")
    return {
        "authorized": authorized,
        "provider_seed": seed if authorized else None,
        "validated_wire_key": "seed" if authorized else None,
        "reason": "authorized" if authorized else "; ".join(reasons),
    }


def fit_to_token_anchor(
    build_text: Callable[[int], str],
    count_tokens: Callable[[str], int],
    *,
    target_tokens: int,
    tolerance_tokens: int = 8,
    max_iterations: int = 48,
) -> dict[str, Any]:
    """Fit a deterministic text builder to a measured token target without provider generation.

    `build_text(char_budget)` and `count_tokens(text)` are injected pure functions.
    The result records the measured token count as actual_L_model_input; character
    count and nominal anchor are never treated as token usage.
    """
    if target_tokens not in FROZEN_ANCHORS:
        raise ContractError(f"target_tokens is not a frozen Layer B anchor: {target_tokens}")
    if not isinstance(tolerance_tokens, int) or tolerance_tokens < 0:
        raise ContractError("tolerance_tokens must be a non-negative integer")
    if max_iterations < 1:
        raise ContractError("max_iterations must be positive")

    low = 1
    high = max(target_tokens * 8, 1024)
    hard_high = target_tokens * 64
    attempts = 0
    best: tuple[int, int, str] | None = None

    def measure(char_budget: int) -> tuple[str, int]:
        nonlocal attempts
        text_a = build_text(char_budget)
        text_b = build_text(char_budget)
        if not isinstance(text_a, str) or text_a != text_b:
            raise ContractError("context builder is not deterministic for the same character budget")
        measured = count_tokens(text_a)
        if not isinstance(measured, int) or isinstance(measured, bool) or measured < 0:
            raise ContractError("token counter must return a non-negative integer")
        attempts += 1
        return text_a, measured

    text_high, count_high = measure(high)
    while count_high < target_tokens - tolerance_tokens and high < hard_high:
        if count_high <= target_tokens:
            best = (high, count_high, text_high)
        low = high + 1
        high = min(high * 2, hard_high)
        text_high, count_high = measure(high)

    low = 1
    for _ in range(max_iterations):
        if low > high:
            break
        mid = (low + high) // 2
        text, measured = measure(mid)
        if measured <= target_tokens:
            if best is None or target_tokens - measured < target_tokens - best[1]:
                best = (mid, measured, text)
        delta = target_tokens - measured
        if 0 <= delta <= tolerance_tokens:
            return {
                "status": "PASS",
                "target_tokens_nominal": target_tokens,
                "tolerance_tokens": tolerance_tokens,
                "actual_L_model_input": measured,
                "character_budget": mid,
                "materialized_characters": len(text),
                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "token_measurement_source": "injected_token_counter",
                "attempts": attempts,
                "provider_generation_performed": False,
            }
        if measured < target_tokens:
            low = mid + 1
        else:
            high = mid - 1

    if best is not None:
        budget, measured, text = best
        delta = target_tokens - measured
        if 0 <= delta <= tolerance_tokens:
            return {
                "status": "PASS",
                "target_tokens_nominal": target_tokens,
                "tolerance_tokens": tolerance_tokens,
                "actual_L_model_input": measured,
                "character_budget": budget,
                "materialized_characters": len(text),
                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "token_measurement_source": "injected_token_counter",
                "attempts": attempts,
                "provider_generation_performed": False,
            }
    raise ContractError(
        f"unable to fit measured token usage to target {target_tokens} within tolerance {tolerance_tokens}"
    )


def validate_token_fit_receipt(receipt: dict[str, Any]) -> None:
    if receipt.get("status") != "PASS":
        raise ContractError("token-fit receipt is not PASS")
    target = receipt.get("target_tokens_nominal")
    measured = receipt.get("actual_L_model_input")
    tolerance = receipt.get("tolerance_tokens")
    if target not in FROZEN_ANCHORS:
        raise ContractError("token-fit receipt target is not frozen")
    if not isinstance(measured, int) or isinstance(measured, bool):
        raise ContractError("token-fit receipt has no measured L_model_input")
    if not isinstance(tolerance, int) or tolerance < 0:
        raise ContractError("token-fit receipt tolerance is invalid")
    if measured > target or target - measured > tolerance:
        raise ContractError("token-fit receipt is outside the admitted tolerance")
    if receipt.get("provider_generation_performed") is not False:
        raise ContractError("no-paid token-fit receipt must record provider_generation_performed=false")


def _provider_pin(provider_tag: str) -> dict[str, Any]:
    tag = str(provider_tag).strip()
    if not tag:
        raise ContractError("provider tag is required")
    return {"only": [tag], "allow_fallbacks": False}


def build_chat_payload(
    *,
    model: str,
    provider_tag: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    token_fit_receipt: dict[str, Any],
    seed_decision: dict[str, Any],
    temperature: float | None = None,
) -> dict[str, Any]:
    validate_token_fit_receipt(token_fit_receipt)
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "provider": _provider_pin(provider_tag),
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if seed_decision.get("authorized") is True:
        seed = seed_decision.get("provider_seed")
        if seed_decision.get("validated_wire_key") != "seed":
            raise ContractError("authorized Chat seed lacks exact validated top-level seed wire key")
        payload["seed"] = _require_uint32(seed)
    return payload


def build_responses_payload(
    *,
    model: str,
    provider_tag: str,
    input_messages: list[dict[str, Any]],
    max_output_tokens: int,
    token_fit_receipt: dict[str, Any],
    seed_decision: dict[str, Any],
    instructions: str | None = None,
    reasoning_effort: str | None = None,
) -> dict[str, Any]:
    validate_token_fit_receipt(token_fit_receipt)
    payload: dict[str, Any] = {
        "model": model,
        "input": input_messages,
        "max_output_tokens": max_output_tokens,
        "provider": _provider_pin(provider_tag),
    }
    if instructions:
        payload["instructions"] = instructions
    if reasoning_effort:
        payload["reasoning"] = {"effort": reasoning_effort}
    if seed_decision.get("authorized") is True:
        seed = seed_decision.get("provider_seed")
        if seed_decision.get("validated_wire_key") != "seed":
            raise ContractError("authorized Responses seed lacks exact validated top-level seed wire key")
        payload["seed"] = _require_uint32(seed)
    return payload
