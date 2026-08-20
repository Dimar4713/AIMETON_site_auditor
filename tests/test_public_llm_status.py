from __future__ import annotations

import json

from app.public_llm_status import (
    project_public_llm_input_metrics,
    project_public_llm_outcome,
)


def test_public_llm_input_metrics_are_allowlisted_and_content_free() -> None:
    metadata = {
        "official_text_chars": 3550,
        "external_context_chars": 52000,
        "external_source_count": 60,
        "schema_chars": 10143,
        "estimated_total_input_chars": 65693,
        "dynamic_input_chars": 65693,
        "model": "deepseek/deepseek-v4-pro",
        "prompt": "PRIVATE PROMPT",
        "raw_response": "PRIVATE RESPONSE",
        "query": "PRIVATE QUERY",
        "url": "https://private.example/secret",
        "provider_payload": {"secret": "value"},
        "outcome": "succeeded",
    }

    projected = project_public_llm_input_metrics(metadata)

    assert projected == {
        "official_text_chars": 3550,
        "external_context_chars": 52000,
        "external_source_count": 60,
        "schema_chars": 10143,
        "estimated_total_input_chars": 65693,
    }
    rendered = json.dumps(projected, ensure_ascii=False)
    for forbidden in (
        "PRIVATE PROMPT",
        "PRIVATE RESPONSE",
        "PRIVATE QUERY",
        "private.example",
        "deepseek",
        "secret",
        "dynamic_input_chars",
    ):
        assert forbidden not in rendered


def test_public_llm_input_metrics_reject_invalid_values_and_clamp_bounds() -> None:
    projected = project_public_llm_input_metrics(
        {
            "official_text_chars": -1,
            "external_context_chars": "999999999999",
            "external_source_count": True,
            "schema_chars": "not-a-number",
            "estimated_total_input_chars": 999_999_999,
        }
    )

    assert projected == {
        "external_context_chars": 10_000_000,
        "estimated_total_input_chars": 30_000_000,
    }


def test_public_llm_outcome_is_closed_allowlist() -> None:
    assert project_public_llm_outcome({"outcome": "succeeded"}) == "succeeded"
    assert project_public_llm_outcome({"outcome": " TIMEOUT "}) == "timeout"
    assert project_public_llm_outcome({"outcome": "failed"}) == "failed"
    assert project_public_llm_outcome({"outcome": "running"}) is None
    assert project_public_llm_outcome({"outcome": {"raw": "secret"}}) is None
    assert project_public_llm_outcome(None) is None
