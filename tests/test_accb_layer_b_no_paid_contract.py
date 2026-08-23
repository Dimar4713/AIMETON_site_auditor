from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import accb_layer_b_no_paid_contract as contract


def _receipt(target: int = 32768, measured: int | None = None, tolerance: int = 8) -> dict:
    if measured is None:
        measured = target
    return {
        "status": "PASS",
        "target_tokens_nominal": target,
        "tolerance_tokens": tolerance,
        "actual_L_model_input": measured,
        "provider_generation_performed": False,
    }


def test_deepseek_retained_no_seed_capability_fails_closed() -> None:
    decision = contract.provider_seed_decision(
        seed_value=1227261303,
        supported_parameters=["reasoning", "max_tokens", "temperature"],
        fresh_endpoint_seed_advertised=False,
        transport_contract_status="PASS",
        validated_wire_key="seed",
    )

    assert decision["authorized"] is False
    assert decision["provider_seed"] is None
    assert "does not advertise seed" in decision["reason"]


def test_sol_responses_omits_seed_while_wire_contract_is_unvalidated() -> None:
    decision = contract.provider_seed_decision(
        seed_value=3297921442,
        supported_parameters=["seed", "reasoning", "max_tokens"],
        fresh_endpoint_seed_advertised=True,
        transport_contract_status="PENDING_NO_PAID_NATIVE_RESPONSES_TEST",
        validated_wire_key=None,
    )
    assert decision["authorized"] is False

    payload = contract.build_responses_payload(
        model="openai/gpt-5.6-sol",
        provider_tag="openai",
        input_messages=[{"role": "user", "content": "bounded test"}],
        max_output_tokens=8192,
        token_fit_receipt=_receipt(),
        seed_decision=decision,
        reasoning_effort="low",
    )

    assert "seed" not in payload
    assert payload["max_output_tokens"] == 8192
    assert payload["reasoning"] == {"effort": "low"}
    assert payload["provider"] == {"only": ["openai"], "allow_fallbacks": False}


def test_authorized_chat_seed_is_exact_top_level_key_only() -> None:
    seed = 3297921442
    decision = contract.provider_seed_decision(
        seed_value=seed,
        supported_parameters=["seed", "reasoning", "max_tokens"],
        fresh_endpoint_seed_advertised=True,
        transport_contract_status="PASS",
        validated_wire_key="seed",
    )
    assert decision == {
        "authorized": True,
        "provider_seed": seed,
        "validated_wire_key": "seed",
        "reason": "authorized",
    }

    payload = contract.build_chat_payload(
        model="z-ai/glm-5.2",
        provider_tag="alibaba",
        messages=[{"role": "user", "content": "bounded test"}],
        max_tokens=8192,
        token_fit_receipt=_receipt(),
        seed_decision=decision,
        temperature=0.0,
    )

    assert payload["seed"] == seed
    assert payload["provider"] == {"only": ["alibaba"], "allow_fallbacks": False}
    assert "seed" not in payload["provider"]
    assert payload.get("reasoning") is None
    assert payload["temperature"] == 0.0


def test_token_fit_uses_injected_measurement_not_character_or_nominal_count() -> None:
    receipt = contract.fit_to_token_anchor(
        lambda char_budget: "x" * char_budget,
        lambda text: len(text) // 4,
        target_tokens=32768,
        tolerance_tokens=0,
    )

    assert receipt["status"] == "PASS"
    assert receipt["target_tokens_nominal"] == 32768
    assert receipt["actual_L_model_input"] == 32768
    assert receipt["character_budget"] == 131072
    assert receipt["materialized_characters"] == 131072
    assert receipt["token_measurement_source"] == "injected_token_counter"
    assert receipt["provider_generation_performed"] is False
    assert receipt["actual_L_model_input"] != receipt["materialized_characters"]


def test_token_fit_fails_closed_when_counter_cannot_reach_anchor() -> None:
    with pytest.raises(contract.ContractError, match="unable to fit measured token usage"):
        contract.fit_to_token_anchor(
            lambda char_budget: "x" * char_budget,
            lambda text: 1,
            target_tokens=32768,
            tolerance_tokens=8,
            max_iterations=12,
        )


def test_invalid_token_fit_receipt_blocks_payload_before_admission() -> None:
    decision = contract.provider_seed_decision(
        seed_value=3297921442,
        supported_parameters=["seed"],
        fresh_endpoint_seed_advertised=True,
        transport_contract_status="PASS",
        validated_wire_key="seed",
    )
    bad_receipt = _receipt(measured=32700, tolerance=8)

    with pytest.raises(contract.ContractError, match="outside the admitted tolerance"):
        contract.build_chat_payload(
            model="qwen/qwen3.7-plus",
            provider_tag="alibaba",
            messages=[{"role": "user", "content": "bounded test"}],
            max_tokens=8192,
            token_fit_receipt=bad_receipt,
            seed_decision=decision,
        )


def test_seed_requires_fresh_endpoint_and_exact_wire_contract() -> None:
    stale_capability = contract.provider_seed_decision(
        seed_value=990456894,
        supported_parameters=["seed"],
        fresh_endpoint_seed_advertised=None,
        transport_contract_status="PASS",
        validated_wire_key="seed",
    )
    wrong_wire = contract.provider_seed_decision(
        seed_value=990456894,
        supported_parameters=["seed"],
        fresh_endpoint_seed_advertised=True,
        transport_contract_status="PASS",
        validated_wire_key="generation.seed",
    )

    assert stale_capability["authorized"] is False
    assert stale_capability["provider_seed"] is None
    assert wrong_wire["authorized"] is False
    assert wrong_wire["provider_seed"] is None
