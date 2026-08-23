#!/usr/bin/env python3
from __future__ import annotations

from typing import Any

from accb_layer_b_no_paid_contract import ContractError, validate_token_fit_receipt

OPENAI_MODEL = "gpt-5.6-sol"
OPENROUTER_MODEL = "openai/gpt-5.6-sol"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
OPENROUTER_RESPONSES_URL = "https://openrouter.ai/api/v1/responses"

FROZEN_ANCHORS = (32768, 131072, 524288)
MAX_OUTPUT_TOKENS = 8192
DOCUMENTED_CONTEXT_TOKENS = 1_050_000
DOCUMENTED_MAX_OUTPUT_TOKENS = 128_000
OPENAI_LONG_CONTEXT_THRESHOLD_TOKENS = 272_000

# OpenAI public pricing observed 2026-08-23. These constants are planning evidence,
# not execution authorization. Fresh pricing must still be rebound before a paid run.
OPENAI_INPUT_USD_PER_M = 5.0
OPENAI_OUTPUT_USD_PER_M = 30.0
OPENAI_LONG_INPUT_MULTIPLIER = 2.0
OPENAI_LONG_OUTPUT_MULTIPLIER = 1.5


class ExternalSolContractError(ContractError):
    pass


def validate_documented_capacity() -> None:
    required = max(FROZEN_ANCHORS) + MAX_OUTPUT_TOKENS
    if DOCUMENTED_CONTEXT_TOKENS < required:
        raise ExternalSolContractError("documented Sol context is below the frozen 512K+output requirement")
    if DOCUMENTED_MAX_OUTPUT_TOKENS < MAX_OUTPUT_TOKENS:
        raise ExternalSolContractError("documented Sol max output is below the frozen output reserve")


def validate_execution_attestation(attestation: dict[str, Any]) -> dict[str, str]:
    """Validate a separately-produced infrastructure region/egress receipt.

    This module deliberately does not carry a country allow-list. Provider country
    policy is mutable and must be checked by a fresh infrastructure preflight.
    """
    if attestation.get("supported_region_attested") is not True:
        raise ExternalSolContractError("execution region has not been freshly attested as supported")
    country = str(attestation.get("egress_country_code") or "").strip().upper()
    runner = str(attestation.get("runner_name") or "").strip()
    source = str(attestation.get("attestation_source") or "").strip()
    if len(country) != 2 or not country.isalpha():
        raise ExternalSolContractError("egress_country_code must be a two-letter code")
    if not runner:
        raise ExternalSolContractError("runner_name is required")
    if not source:
        raise ExternalSolContractError("attestation_source is required")
    return {
        "egress_country_code": country,
        "runner_name": runner,
        "attestation_source": source,
    }


def _require_frozen_fit(receipt: dict[str, Any]) -> None:
    validate_token_fit_receipt(receipt)
    if receipt.get("target_tokens_nominal") not in FROZEN_ANCHORS:
        raise ExternalSolContractError("token fit target is not a frozen Layer B anchor")


def _base_responses_payload(
    *,
    model: str,
    input_items: list[dict[str, Any]],
    token_fit_receipt: dict[str, Any],
) -> dict[str, Any]:
    _require_frozen_fit(token_fit_receipt)
    validate_documented_capacity()
    if not isinstance(input_items, list) or not input_items:
        raise ExternalSolContractError("input_items must be a non-empty list")
    return {
        "model": model,
        "input": input_items,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "reasoning": {"effort": "low"},
        "store": False,
    }


def build_direct_openai_responses_contract(
    *,
    input_items: list[dict[str, Any]],
    token_fit_receipt: dict[str, Any],
    execution_attestation: dict[str, Any],
) -> dict[str, Any]:
    route = validate_execution_attestation(execution_attestation)
    payload = _base_responses_payload(
        model=OPENAI_MODEL,
        input_items=input_items,
        token_fit_receipt=token_fit_receipt,
    )
    if "seed" in payload:
        raise ExternalSolContractError("direct OpenAI Responses seed is not validated for this benchmark")
    return {
        "transport": "openai-responses",
        "url": OPENAI_RESPONSES_URL,
        "payload": payload,
        "provider_pin": "openai-direct",
        "allow_fallbacks": False,
        "execution": route,
        "provider_generation_performed": False,
        "paid_spend_authorized": False,
    }


def build_openrouter_responses_contract(
    *,
    input_items: list[dict[str, Any]],
    token_fit_receipt: dict[str, Any],
    execution_attestation: dict[str, Any],
    provider_slug: str,
    require_zdr: bool = False,
) -> dict[str, Any]:
    route = validate_execution_attestation(execution_attestation)
    provider = str(provider_slug).strip()
    if not provider:
        raise ExternalSolContractError("OpenRouter provider_slug is required")
    payload = _base_responses_payload(
        model=OPENROUTER_MODEL,
        input_items=input_items,
        token_fit_receipt=token_fit_receipt,
    )
    provider_policy: dict[str, Any] = {
        "only": [provider],
        "order": [provider],
        "allow_fallbacks": False,
        "require_parameters": True,
        "data_collection": "deny",
    }
    if require_zdr:
        provider_policy["zdr"] = True
    payload["provider"] = provider_policy
    if "seed" in payload:
        raise ExternalSolContractError("OpenRouter Responses seed is not validated for this benchmark")
    return {
        "transport": "openrouter-responses",
        "url": OPENROUTER_RESPONSES_URL,
        "payload": payload,
        "provider_pin": provider,
        "allow_fallbacks": False,
        "execution": route,
        "provider_generation_performed": False,
        "paid_spend_authorized": False,
    }


def estimate_direct_openai_sol_usd(prompt_tokens: int, output_tokens: int = MAX_OUTPUT_TOKENS) -> dict[str, Any]:
    if not isinstance(prompt_tokens, int) or prompt_tokens < 0:
        raise ExternalSolContractError("prompt_tokens must be a non-negative integer")
    if not isinstance(output_tokens, int) or output_tokens < 0:
        raise ExternalSolContractError("output_tokens must be a non-negative integer")
    long_context = prompt_tokens > OPENAI_LONG_CONTEXT_THRESHOLD_TOKENS
    input_rate = OPENAI_INPUT_USD_PER_M * (OPENAI_LONG_INPUT_MULTIPLIER if long_context else 1.0)
    output_rate = OPENAI_OUTPUT_USD_PER_M * (OPENAI_LONG_OUTPUT_MULTIPLIER if long_context else 1.0)
    estimate = prompt_tokens * input_rate / 1_000_000 + output_tokens * output_rate / 1_000_000
    return {
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "long_context_pricing_applied": long_context,
        "input_usd_per_m": input_rate,
        "output_usd_per_m": output_rate,
        "estimated_cost_usd": round(estimate, 6),
        "execution_authorized": False,
    }


def estimate_openrouter_sol_usd(
    *,
    prompt_tokens: int,
    output_tokens: int,
    fresh_input_usd_per_m: float,
    fresh_output_usd_per_m: float,
) -> dict[str, Any]:
    if not isinstance(prompt_tokens, int) or prompt_tokens < 0:
        raise ExternalSolContractError("prompt_tokens must be a non-negative integer")
    if not isinstance(output_tokens, int) or output_tokens < 0:
        raise ExternalSolContractError("output_tokens must be a non-negative integer")
    for label, rate in (("fresh_input_usd_per_m", fresh_input_usd_per_m), ("fresh_output_usd_per_m", fresh_output_usd_per_m)):
        if isinstance(rate, bool) or not isinstance(rate, (int, float)) or rate <= 0:
            raise ExternalSolContractError(f"{label} must be positive")
    estimate = prompt_tokens * fresh_input_usd_per_m / 1_000_000 + output_tokens * fresh_output_usd_per_m / 1_000_000
    return {
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "input_usd_per_m": float(fresh_input_usd_per_m),
        "output_usd_per_m": float(fresh_output_usd_per_m),
        "estimated_cost_usd": round(estimate, 6),
        "pricing_source": "fresh_injected_openrouter_metadata",
        "execution_authorized": False,
    }
