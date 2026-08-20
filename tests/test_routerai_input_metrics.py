from __future__ import annotations

import json

from app.models import SiteAnalysis
from app.routerai_evidence_units import DEFAULT_EVIDENCE_CHUNK_CHARS
from app.routerai_runtime import routerai_input_metrics


def test_routerai_input_metrics_are_truthful_untruncated_and_content_free() -> None:
    text = "x" * 40000
    sources = [
        {
            "id": "E1",
            "title": "Sensitive title must not be copied to metrics",
            "url": "https://example.test/private",
            "snippet": "secret-looking-content" * 5000,
        },
        {"id": "E2", "snippet": "small"},
    ]

    metrics = routerai_input_metrics(text, sources)
    serialized_sources = json.dumps(sources, ensure_ascii=False, separators=(",", ":"))

    assert set(metrics) == {
        "model",
        "official_text_chars",
        "external_context_chars",
        "external_source_count",
        "schema_chars",
        "estimated_total_input_chars",
        "dynamic_input_chars",
        "official_chunks_estimated",
        "external_chunks_estimated",
        "input_truncated",
        "projected_external_chars_total",
        "projected_external_source_refs_total",
        "unique_projected_external_chars",
        "projection_duplication_ratio_x1000",
    }
    assert metrics["official_text_chars"] == len(text)
    assert metrics["external_context_chars"] == len(serialized_sources)
    assert metrics["external_source_count"] == 2
    assert metrics["schema_chars"] == len(
        json.dumps(SiteAnalysis.model_json_schema(), ensure_ascii=False)
    )
    expected_total = len(text) + len(serialized_sources) + metrics["schema_chars"]
    assert metrics["estimated_total_input_chars"] == expected_total
    assert metrics["dynamic_input_chars"] == expected_total
    assert metrics["official_chunks_estimated"] == 4
    assert metrics["external_chunks_estimated"] == (
        len(serialized_sources) + DEFAULT_EVIDENCE_CHUNK_CHARS - 1
    ) // DEFAULT_EVIDENCE_CHUNK_CHARS
    assert metrics["input_truncated"] is False
    assert metrics["model"]
    for key in (
        "projected_external_chars_total",
        "projected_external_source_refs_total",
        "unique_projected_external_chars",
        "projection_duplication_ratio_x1000",
    ):
        assert isinstance(metrics[key], int)
        assert metrics[key] >= 0

    rendered = json.dumps(metrics, ensure_ascii=False)
    assert "Sensitive title" not in rendered
    assert "example.test" not in rendered
    assert "secret-looking-content" not in rendered
    assert "api_key" not in rendered.lower()
