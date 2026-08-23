from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import accb_layer_b_endpoint_census as census


def _endpoint(
    *,
    tag: str,
    apis: list[str] | None = None,
    context: int = 1_000_000,
    max_prompt: int = 900_000,
    max_completion: int = 100_000,
    prompt: float = 0.0001,
    completion: float = 0.0005,
    status: int = 0,
    supported_parameters: list[str] | None = None,
    variable_pricings: list[dict] | None = None,
) -> dict:
    return {
        "name": f"Provider | {tag}",
        "provider_name": tag.title(),
        "tag": tag,
        "country": "test",
        "context_length": context,
        "max_prompt_tokens": max_prompt,
        "max_completion_tokens": max_completion,
        "status": status,
        "supported_apis": apis or ["chat"],
        "supported_parameters": supported_parameters or ["seed", "max_tokens"],
        "pricing": {"prompt": prompt, "completion": completion},
        "variable_pricings": variable_pricings or [],
    }


def _payload(*endpoints: dict) -> dict:
    return {"data": {"endpoints": list(endpoints)}}


def test_select_endpoint_skips_first_priority_route_if_512k_capacity_is_not_proven() -> None:
    too_small = _endpoint(tag="cheap", max_prompt=128000, context=262144)
    eligible = _endpoint(tag="long")
    chosen = census.select_endpoint("z-ai/glm-5.2", _payload(too_small, eligible))
    assert chosen["tag"] == "long"
    assert chosen["_routerai_priority_index"] == 1
    assert chosen["_rejections_before_choice"][0]["tag"] == "cheap"
    assert "max_prompt_tokens_below_524288_or_unknown" in (
        chosen["_rejections_before_choice"][0]["reasons"]
    )


def test_select_endpoint_fails_closed_when_max_prompt_is_unknown() -> None:
    endpoint = _endpoint(tag="unknown")
    endpoint["max_prompt_tokens"] = None
    with pytest.raises(census.CensusError, match="no eligible chat endpoint"):
        census.select_endpoint("qwen/qwen3.7-plus", _payload(endpoint))


def test_sol_selection_requires_responses_transport() -> None:
    chat_only = _endpoint(tag="chat-only", apis=["chat"])
    responses = _endpoint(tag="openai", apis=["responses"], supported_parameters=["seed", "reasoning"])
    chosen = census.select_endpoint("openai/gpt-5.6-sol", _payload(chat_only, responses))
    assert chosen["tag"] == "openai"
    assert chosen["_required_transport"] == "responses"
    assert chosen["_routerai_priority_index"] == 1


def test_prompt_threshold_changes_both_input_and_output_rates() -> None:
    endpoint = _endpoint(
        tag="tiered",
        prompt=0.0001,
        completion=0.0005,
        variable_pricings=[
            {
                "type": "prompt-threshold",
                "threshold": 272000,
                "prompt": 0.0002,
                "completion": 0.00075,
            }
        ],
    )
    low = census.cell_cost(endpoint, 131072)
    high = census.cell_cost(endpoint, 524288)
    assert low["prompt_rate_rub_per_token"] == 0.0001
    assert low["completion_rate_rub_per_token"] == 0.0005
    assert high["prompt_rate_rub_per_token"] == 0.0002
    assert high["completion_rate_rub_per_token"] == 0.00075
    assert high["applied_variable_pricing"][0]["threshold"] == 272000


def test_unknown_dynamic_pricing_is_reserved_at_max_rate_when_rates_are_visible() -> None:
    endpoint = _endpoint(
        tag="dynamic",
        prompt=0.0001,
        completion=0.0005,
        variable_pricings=[
            {"type": "time-of-day", "prompt": 0.0003, "completion": 0.0009}
        ],
    )
    row = census.cell_cost(endpoint, 32768)
    assert row["prompt_rate_rub_per_token"] == 0.0003
    assert row["completion_rate_rub_per_token"] == 0.0009
    assert row["applied_variable_pricing"][0]["mode"] == "conservative_max_rate"


def test_unbounded_variable_pricing_fails_closed() -> None:
    endpoint = _endpoint(
        tag="unbounded",
        variable_pricings=[{"type": "mystery", "threshold": 10}],
    )
    with pytest.raises(census.CensusError, match="unbounded variable pricing"):
        census.cell_cost(endpoint, 32768)


def test_full_census_report_is_read_only_pinned_and_15_cells() -> None:
    payloads = {
        "z-ai/glm-5.2": _payload(_endpoint(tag="glm", apis=["chat"])),
        "deepseek/deepseek-v4-pro-0813": _payload(
            _endpoint(tag="deepseek", apis=["chat"], supported_parameters=["max_tokens"])
        ),
        "qwen/qwen3.7-plus": _payload(_endpoint(tag="qwen", apis=["chat"])),
        "moonshotai/kimi-k3": _payload(_endpoint(tag="kimi", apis=["chat"])),
        "openai/gpt-5.6-sol": _payload(
            _endpoint(tag="openai", apis=["responses"], supported_parameters=["seed", "reasoning"])
        ),
    }

    def fake_fetcher(url: str) -> dict:
        for model_id, payload in payloads.items():
            if url == census.endpoint_url(model_id):
                return payload
        raise AssertionError(url)

    report = census.build_census_report(fetcher=fake_fetcher)
    assert report["status"] == "READ_ONLY_CENSUS_NO_MODEL_GENERATION"
    assert report["authorization_header_sent"] is False
    assert report["routerai_generation_calls_performed"] == 0
    assert report["spend_authorized_rub"] == 0
    assert report["planned_calls"] == 15
    assert report["paid_execution_authorized"] is False
    assert report["capacity_gate"]["max_anchor_tokens"] == 524288
    assert report["capacity_gate"]["total_context_required"] == 532480
    assert all(row["provider_pin_required"] is True for row in report["cells"])
    assert all(row["allow_fallbacks"] is False for row in report["cells"])
    assert report["selected_endpoints"]["deepseek/deepseek-v4-pro-0813"]["seed_advertised"] is False
    assert report["selected_endpoints"]["openai/gpt-5.6-sol"]["required_transport"] == "responses"
