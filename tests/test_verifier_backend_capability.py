from __future__ import annotations

import pytest

from app.verifier_backend_capability import (
    build_openai_logprob_probe_payload,
    qualify_openai_logprob_response,
    routerai_contract_candidate,
)


def _response(top_logprobs):
    return {
        "choices": [
            {
                "message": {"content": "A"},
                "logprobs": {
                    "content": [
                        {
                            "token": "A",
                            "logprob": -0.1,
                            "top_logprobs": top_logprobs,
                        }
                    ]
                },
            }
        ]
    }


def test_routerai_contract_candidate_is_not_runtime_qualified():
    report = routerai_contract_candidate("openai/gpt-4o-mini")

    assert report.qualification_status == "contract_candidate"
    assert report.documented_logprobs is True
    assert report.documented_top_logprobs is True
    assert report.runtime_logprobs is False
    assert report.client_release_authority is False
    assert report.hard_gate_override is False


def test_probe_payload_is_tiny_and_requests_distribution():
    payload = build_openai_logprob_probe_payload("openai/gpt-4o-mini")

    assert payload["logprobs"] is True
    assert payload["top_logprobs"] == 20
    assert payload["max_tokens"] == 4
    assert payload["temperature"] == 0


def test_probe_payload_rejects_invalid_top_logprobs():
    with pytest.raises(ValueError):
        build_openai_logprob_probe_payload("model", top_logprobs=21)


def test_runtime_qualified_requires_visible_score_token_and_nondegenerate_distribution():
    body = _response(
        [
            {"token": "A", "logprob": -0.1},
            {"token": "B", "logprob": -1.2},
            {"token": "C", "logprob": -2.1},
        ]
    )

    report = qualify_openai_logprob_response(body, backend_id="routerai", model="model-x")

    assert report.qualification_status == "runtime_qualified"
    assert report.runtime_logprobs is True
    assert report.runtime_top_logprobs is True
    assert report.score_token_visible is True
    assert report.nondegenerate_distribution is True
    assert report.measured_top_logprobs_width == 3


def test_missing_logprob_content_is_incapable_not_neutral():
    report = qualify_openai_logprob_response(
        {"choices": [{"message": {"content": "A"}}]},
        backend_id="routerai",
        model="model-x",
    )

    assert report.qualification_status == "runtime_incapable"
    assert "missing_logprob_content" in report.reason_codes


def test_missing_score_tokens_is_degraded():
    body = _response(
        [
            {"token": "yes", "logprob": -0.1},
            {"token": "no", "logprob": -1.4},
        ]
    )

    report = qualify_openai_logprob_response(body, backend_id="routerai", model="model-x")

    assert report.qualification_status == "runtime_degraded"
    assert report.score_token_visible is False
    assert "score_token_not_visible" in report.reason_codes


def test_flat_distribution_is_degraded():
    body = _response(
        [
            {"token": "A", "logprob": -1.0},
            {"token": "B", "logprob": -1.0},
            {"token": "C", "logprob": -1.0},
        ]
    )

    report = qualify_openai_logprob_response(body, backend_id="routerai", model="model-x")

    assert report.qualification_status == "runtime_degraded"
    assert report.nondegenerate_distribution is False
    assert "degenerate_logprob_distribution" in report.reason_codes
