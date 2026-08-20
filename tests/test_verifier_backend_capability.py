from __future__ import annotations

import pytest

from app.verifier_backend_capability import (
    SCORE_TOKENS,
    build_openai_logprob_probe_payload,
    build_openai_structured_score_probe_payload,
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
    assert report.documented_structured_output is True
    assert report.runtime_logprobs is False
    assert report.client_release_authority is False
    assert report.hard_gate_override is False


def test_probe_payload_is_tiny_and_requests_distribution():
    payload = build_openai_logprob_probe_payload("openai/gpt-4o-mini")

    assert payload["logprobs"] is True
    assert payload["top_logprobs"] == 20
    assert payload["max_tokens"] == 4
    assert payload["temperature"] == 0


def test_structured_probe_constrains_score_to_exact_a_t_enum():
    payload = build_openai_structured_score_probe_payload("openai/gpt-4o-mini")

    assert payload["logprobs"] is True
    assert payload["top_logprobs"] == 20
    assert payload["temperature"] == 1
    schema = payload["response_format"]["json_schema"]
    assert schema["strict"] is True
    assert schema["schema"]["properties"]["score"]["enum"] == list(SCORE_TOKENS)
    assert schema["schema"]["additionalProperties"] is False


def test_probe_payload_rejects_invalid_top_logprobs():
    with pytest.raises(ValueError):
        build_openai_logprob_probe_payload("model", top_logprobs=21)
    with pytest.raises(ValueError):
        build_openai_structured_score_probe_payload("model", top_logprobs=0)


def test_runtime_qualified_requires_two_distinct_score_alternatives():
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
    assert report.evidence["max_score_support"] == 3


def test_singleton_score_support_is_degraded_even_when_other_tokens_have_logprobs():
    body = _response(
        [
            {"token": "A", "logprob": -0.1},
            {"token": " ordinary", "logprob": -0.4},
            {"token": " token", "logprob": -1.1},
        ]
    )

    report = qualify_openai_logprob_response(body, backend_id="routerai", model="model-x")

    assert report.qualification_status == "runtime_degraded"
    assert report.score_token_visible is True
    assert report.nondegenerate_distribution is False
    assert report.evidence["max_score_support"] == 1
    assert "singleton_score_distribution" in report.reason_codes


def test_json_token_fragments_are_recognized_as_score_alternatives():
    body = _response(
        [
            {"token": '"A"', "logprob": -0.2},
            {"token": '"B"', "logprob": -0.5},
            {"token": '"C"', "logprob": -1.4},
        ]
    )
    report = qualify_openai_logprob_response(body, backend_id="routerai", model="model-x")
    assert report.qualification_status == "runtime_qualified"
    assert report.evidence["max_score_support"] == 3


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


def test_equal_probability_score_support_is_still_a_real_distribution():
    body = _response(
        [
            {"token": "A", "logprob": -1.0},
            {"token": "B", "logprob": -1.0},
            {"token": "C", "logprob": -1.0},
        ]
    )

    report = qualify_openai_logprob_response(body, backend_id="routerai", model="model-x")

    assert report.qualification_status == "runtime_qualified"
    assert report.nondegenerate_distribution is True
    assert report.evidence["max_score_support"] == 3
