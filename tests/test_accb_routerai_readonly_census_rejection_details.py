from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import accb_routerai_readonly_census as census


def _body(endpoint: dict) -> dict:
    return {"data": {"endpoints": [endpoint]}}


def _endpoint(**updates) -> dict:
    row = {
        "provider_name": "OpenAI",
        "tag": "openai",
        "status": 0,
        "context_length": 1_050_000,
        "max_prompt_tokens": 922_000,
        "max_completion_tokens": 128_000,
        "supported_apis": ["responses"],
        "supported_parameters": ["max_tokens", "seed", "reasoning"],
        "pricing": {"prompt": 0.001, "completion": 0.002},
        "variable_pricings": [],
    }
    row.update(updates)
    return row


def test_capacity_rejection_receipt_explains_exact_safe_reason() -> None:
    with pytest.raises(census.CensusError) as excinfo:
        census.select_endpoint(
            "openai/gpt-5.6-sol",
            _body(_endpoint(context_length=500_000)),
        )

    details = excinfo.value.details
    assert details["model"] == "openai/gpt-5.6-sol"
    assert details["required_prompt_tokens"] == 524288
    assert details["required_output_reserve_tokens"] == 8192
    observed = details["observed_endpoints"][0]
    assert observed["tag"] == "openai"
    assert observed["context_length"] == 500_000
    assert "context_length_below_prompt_plus_output_reserve" in observed["rejection_reasons"]


def test_transport_and_status_rejections_are_observable() -> None:
    with pytest.raises(census.CensusError) as excinfo:
        census.select_endpoint(
            "openai/gpt-5.6-sol",
            _body(_endpoint(status=-2, supported_apis=[])),
        )

    observed = excinfo.value.details["observed_endpoints"][0]
    assert "supported_chat_or_responses_transport_missing" in observed["rejection_reasons"]
    assert "endpoint_status_negative" in observed["rejection_reasons"]


def test_completion_capacity_rejection_is_observable() -> None:
    with pytest.raises(census.CensusError) as excinfo:
        census.select_endpoint(
            "openai/gpt-5.6-sol",
            _body(_endpoint(max_completion_tokens=4096)),
        )

    observed = excinfo.value.details["observed_endpoints"][0]
    assert "max_completion_tokens_below_8192" in observed["rejection_reasons"]


def test_failure_receipt_carries_allowlisted_details_only() -> None:
    endpoint = _endpoint(context_length=500_000)
    endpoint["secret_prompt"] = "MUST_NOT_BE_RETAINED"
    endpoint["arbitrary_provider_blob"] = {"text": "MUST_NOT_BE_RETAINED_EITHER"}

    with pytest.raises(census.CensusError) as excinfo:
        census.select_endpoint("openai/gpt-5.6-sol", _body(endpoint))

    receipt = census.failure_receipt(excinfo.value)
    serialized = repr(receipt)
    assert "safe_details" in receipt["failure"]
    assert "MUST_NOT_BE_RETAINED" not in serialized
    assert "arbitrary_provider_blob" not in serialized
    observed = receipt["failure"]["safe_details"]["observed_endpoints"][0]
    assert set(observed) == {
        "provider_name",
        "tag",
        "status",
        "context_length",
        "max_prompt_tokens",
        "max_completion_tokens",
        "supported_apis",
        "supported_parameters",
        "pricing_object_present",
        "prompt_price_present",
        "completion_price_present",
        "variable_pricing_types",
        "selected_transport_if_eligible",
        "rejection_reasons",
    }
