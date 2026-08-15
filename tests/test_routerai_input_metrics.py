from __future__ import annotations

import json

from app.models import SiteAnalysis
from app.routerai_runtime import routerai_input_metrics


def test_routerai_input_metrics_are_bounded_and_content_free() -> None:
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

    assert metrics["official_text_chars"] == 30000
    assert 0 < metrics["external_context_chars"] <= 52000
    assert metrics["external_source_count"] == 2
    assert metrics["schema_chars"] == len(
        json.dumps(SiteAnalysis.model_json_schema(), ensure_ascii=False)
    )
    assert metrics["dynamic_input_chars"] == (
        metrics["official_text_chars"]
        + metrics["external_context_chars"]
        + metrics["schema_chars"]
    )
    assert metrics["model"]

    rendered = json.dumps(metrics, ensure_ascii=False)
    assert "Sensitive title" not in rendered
    assert "example.test" not in rendered
    assert "secret-looking-content" not in rendered
    assert "api_key" not in rendered.lower()
