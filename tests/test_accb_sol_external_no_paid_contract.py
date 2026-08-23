from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import accb_sol_external_no_paid_contract as external


def _receipt(target: int = 32768) -> dict:
    return {
        "status": "PASS",
        "target_tokens_nominal": target,
        "tolerance_tokens": 8,
        "actual_L_model_input": target,
        "provider_generation_performed": False,
    }


def _attestation() -> dict:
    return {
        "supported_region_attested": True,
        "egress_country_code": "nl",
        "runner_name": "aimeton-accb-external-01",
        "attestation_source": "fresh-infrastructure-preflight",
    }


def _input() -> list[dict]:
    return [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "bounded ACCB context"}],
        }
    ]


def test_documented_sol_capacity_keeps_frozen_512k_anchor_admissible() -> None:
    external.validate_documented_capacity()
    assert external.DOCUMENTED_CONTEXT_TOKENS >= 524288 + 8192
    assert external.DOCUMENTED_MAX_OUTPUT_TOKENS >= 8192


def test_direct_openai_contract_is_exact_model_responses_no_seed_no_fallback() -> None:
    contract = external.build_direct_openai_responses_contract(
        input_items=_input(),
        token_fit_receipt=_receipt(524288),
        execution_attestation=_attestation(),
    )

    assert contract["transport"] == "openai-responses"
    assert contract["url"] == "https://api.openai.com/v1/responses"
    assert contract["provider_pin"] == "openai-direct"
    assert contract["allow_fallbacks"] is False
    assert contract["execution"]["egress_country_code"] == "NL"
    assert contract["provider_generation_performed"] is False
    assert contract["paid_spend_authorized"] is False

    payload = contract["payload"]
    assert payload["model"] == "gpt-5.6-sol"
    assert payload["max_output_tokens"] == 8192
    assert payload["reasoning"] == {"effort": "low"}
    assert payload["store"] is False
    assert "seed" not in payload
    assert "provider" not in payload
    assert "models" not in payload


def test_openrouter_contract_pins_one_provider_and_disables_fallbacks() -> None:
    contract = external.build_openrouter_responses_contract(
        input_items=_input(),
        token_fit_receipt=_receipt(131072),
        execution_attestation=_attestation(),
        provider_slug="openai",
    )

    assert contract["transport"] == "openrouter-responses"
    assert contract["url"] == "https://openrouter.ai/api/v1/responses"
    assert contract["provider_pin"] == "openai"
    assert contract["allow_fallbacks"] is False
    assert contract["provider_generation_performed"] is False
    assert contract["paid_spend_authorized"] is False

    payload = contract["payload"]
    assert payload["model"] == "openai/gpt-5.6-sol"
    assert payload["store"] is False
    assert "seed" not in payload
    assert "models" not in payload
    assert payload["provider"] == {
        "only": ["openai"],
        "order": ["openai"],
        "allow_fallbacks": False,
        "require_parameters": True,
        "data_collection": "deny",
    }


def test_openrouter_zdr_is_explicit_and_never_implicit() -> None:
    default = external.build_openrouter_responses_contract(
        input_items=_input(),
        token_fit_receipt=_receipt(),
        execution_attestation=_attestation(),
        provider_slug="azure",
    )
    zdr = external.build_openrouter_responses_contract(
        input_items=_input(),
        token_fit_receipt=_receipt(),
        execution_attestation=_attestation(),
        provider_slug="azure",
        require_zdr=True,
    )

    assert "zdr" not in default["payload"]["provider"]
    assert zdr["payload"]["provider"]["zdr"] is True


def test_external_contract_fails_closed_without_fresh_supported_region_attestation() -> None:
    bad = _attestation()
    bad["supported_region_attested"] = False

    with pytest.raises(external.ExternalSolContractError, match="not been freshly attested"):
        external.build_direct_openai_responses_contract(
            input_items=_input(),
            token_fit_receipt=_receipt(),
            execution_attestation=bad,
        )


def test_external_contract_rejects_invalid_token_fit_before_provider_admission() -> None:
    bad = _receipt()
    bad["actual_L_model_input"] = 32000

    with pytest.raises(external.ContractError):
        external.build_openrouter_responses_contract(
            input_items=_input(),
            token_fit_receipt=bad,
            execution_attestation=_attestation(),
            provider_slug="openai",
        )


def test_direct_openai_planning_cost_applies_long_context_multiplier_only_above_272k() -> None:
    low = external.estimate_direct_openai_sol_usd(32768)
    middle = external.estimate_direct_openai_sol_usd(131072)
    high = external.estimate_direct_openai_sol_usd(524288)

    assert low["long_context_pricing_applied"] is False
    assert middle["long_context_pricing_applied"] is False
    assert high["long_context_pricing_applied"] is True
    assert low["estimated_cost_usd"] == pytest.approx(0.4096)
    assert middle["estimated_cost_usd"] == pytest.approx(0.90112)
    assert high["estimated_cost_usd"] == pytest.approx(5.61152)
    assert sum(row["estimated_cost_usd"] for row in (low, middle, high)) == pytest.approx(6.92224)
    assert all(row["execution_authorized"] is False for row in (low, middle, high))


def test_openrouter_estimate_requires_fresh_injected_price_and_authorizes_nothing() -> None:
    estimate = external.estimate_openrouter_sol_usd(
        prompt_tokens=524288,
        output_tokens=8192,
        fresh_input_usd_per_m=2.5,
        fresh_output_usd_per_m=15.0,
    )

    assert estimate["estimated_cost_usd"] == pytest.approx(1.4336)
    assert estimate["pricing_source"] == "fresh_injected_openrouter_metadata"
    assert estimate["execution_authorized"] is False

    with pytest.raises(external.ExternalSolContractError, match="must be positive"):
        external.estimate_openrouter_sol_usd(
            prompt_tokens=32768,
            output_tokens=8192,
            fresh_input_usd_per_m=0,
            fresh_output_usd_per_m=15.0,
        )
