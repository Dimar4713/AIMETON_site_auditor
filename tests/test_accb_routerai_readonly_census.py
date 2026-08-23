from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import accb_routerai_readonly_census as census


def _endpoint(
    *,
    tag: str = "provider",
    prompt: float = 0.001,
    completion: float = 0.002,
    variable: list[dict] | None = None,
    supported_parameters: list[str] | None = None,
    context_length: int = 1_048_576,
    max_prompt_tokens: int | None = 900_000,
) -> dict:
    return {
        "name": "fixture",
        "provider_name": "Fixture Provider",
        "tag": tag,
        "status": 0,
        "context_length": context_length,
        "max_prompt_tokens": max_prompt_tokens,
        "max_completion_tokens": 128_000,
        "supported_apis": ["chat"],
        "supported_parameters": supported_parameters or ["max_tokens"],
        "pricing": {"prompt": prompt, "completion": completion},
        "variable_pricings": variable or [],
    }


def _body(endpoint: dict) -> dict:
    return {"data": {"endpoints": [endpoint]}}


def test_source_is_get_only_and_contains_no_generation_endpoint_or_routerai_auth() -> None:
    source = (SCRIPTS / "accb_routerai_readonly_census.py").read_text(encoding="utf-8")
    assert 'method="GET"' in source
    assert '"Authorization"' not in source
    assert "/chat/completions" not in source
    assert 'f"{BASE_URL}/responses"' not in source
    assert "provider_generations_performed" in source
    assert "routerai_authorization_header_sent" in source


def test_prompt_threshold_applies_only_above_threshold() -> None:
    selected = census.select_endpoint(
        "qwen/qwen3.7-plus",
        _body(
            _endpoint(
                prompt=0.001,
                completion=0.002,
                variable=[
                    {
                        "type": "prompt-threshold",
                        "threshold": 256000,
                        "prompt": 0.003,
                        "completion": 0.006,
                    }
                ],
            )
        ),
    )
    priced = census.price_endpoint(selected)

    assert priced["anchors"]["32768"]["prompt_rate_rub_per_token"] == 0.001
    assert priced["anchors"]["131072"]["prompt_rate_rub_per_token"] == 0.001
    assert priced["anchors"]["524288"]["prompt_rate_rub_per_token"] == 0.003
    assert "prompt-threshold" not in priced["anchors"]["131072"]["applied_pricing_classes"]
    assert "prompt-threshold" in priced["anchors"]["524288"]["applied_pricing_classes"]


def test_time_of_day_uses_highest_advertised_rate_for_every_anchor() -> None:
    selected = census.select_endpoint(
        "deepseek/deepseek-v4-pro-0813",
        _body(
            _endpoint(
                prompt=0.001,
                completion=0.002,
                variable=[
                    {"type": "time-of-day", "utc_start": 0, "utc_end": 100, "prompt": 0.001, "completion": 0.002},
                    {"type": "time-of-day", "utc_start": 100, "utc_end": 400, "prompt": 0.004, "completion": 0.008},
                ],
            )
        ),
    )
    priced = census.price_endpoint(selected)

    for anchor in census.ANCHORS:
        row = priced["anchors"][str(anchor)]
        assert row["prompt_rate_rub_per_token"] == 0.004
        assert row["completion_rate_rub_per_token"] == 0.008
        assert "time-of-day" in row["applied_pricing_classes"]


def test_unknown_variable_pricing_type_fails_closed() -> None:
    with pytest.raises(census.CensusError, match="unsupported variable pricing type"):
        census.select_endpoint(
            "z-ai/glm-5.2",
            _body(_endpoint(variable=[{"type": "mystery", "prompt": 0.002}])),
        )


def test_endpoint_must_physically_support_largest_anchor() -> None:
    with pytest.raises(census.CensusError, match="no healthy priced endpoint"):
        census.select_endpoint(
            "moonshotai/kimi-k3",
            _body(_endpoint(context_length=500_000, max_prompt_tokens=490_000)),
        )


def test_census_records_five_models_seed_capability_and_zero_generation() -> None:
    calls: list[str] = []

    def fake_get(url: str) -> dict:
        calls.append(url)
        model_slug = url.split("/models/", 1)[1].rsplit("/endpoints", 1)[0]
        tag = "openai" if model_slug == "openai/gpt-5.6-sol" else "fixture"
        return _body(_endpoint(tag=tag, supported_parameters=["max_tokens", "seed"]))

    result = census.census(fake_get)

    assert len(calls) == 5
    assert len(result["models"]) == 5
    assert result["planned_cells"] == 15
    assert result["provider_generations_performed"] == 0
    assert result["paid_spend_authorized_rub"] == 0
    assert result["routerai_authorization_header_sent"] is False
    assert result["http_methods"] == ["GET"]
    assert result["whole_tranche_conservative_estimate_rub"] > 0
    assert all(row["seed_advertised_fresh"] is True for row in result["models"])
