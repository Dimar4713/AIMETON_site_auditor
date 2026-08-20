from __future__ import annotations

from app.routerai_projection_metrics import routerai_projection_metrics


def test_projection_metrics_measure_slice_duplication_without_content() -> None:
    sources = [
        {
            "id": "s1",
            "title": "Registry",
            "query_kind": "registry",
            "result_kind": "registry",
            "source_class": "registry",
            "evidence_level": "secondary",
            "snippet": "PRIVATE REGISTRY CONTENT",
            "url": "https://private.example/registry",
        },
        {
            "id": "s2",
            "title": "Social",
            "query_kind": "social",
            "result_kind": "social",
            "source_class": "social",
            "evidence_level": "secondary",
            "snippet": "PRIVATE SOCIAL CONTENT",
            "url": "https://private.example/social",
        },
        {
            "id": "s3",
            "title": "Finance",
            "query_kind": "finance",
            "result_kind": "finance",
            "source_class": "finance",
            "evidence_level": "secondary",
            "snippet": "PRIVATE FINANCE CONTENT",
            "url": "https://private.example/finance",
        },
    ]

    metrics = routerai_projection_metrics(sources)

    assert metrics["projected_external_chars_total"] > metrics["unique_projected_external_chars"]
    assert metrics["projected_external_source_refs_total"] > len(sources)
    assert metrics["projection_duplication_ratio_x1000"] > 1000
    assert set(metrics) == {
        "projected_external_chars_total",
        "projected_external_source_refs_total",
        "unique_projected_external_chars",
        "projection_duplication_ratio_x1000",
    }
    assert all(isinstance(value, int) and value >= 0 for value in metrics.values())
    rendered = repr(metrics)
    assert "PRIVATE" not in rendered
    assert "private.example" not in rendered


def test_projection_metrics_are_zero_without_sources() -> None:
    assert routerai_projection_metrics([]) == {
        "projected_external_chars_total": 0,
        "projected_external_source_refs_total": 0,
        "unique_projected_external_chars": 0,
        "projection_duplication_ratio_x1000": 0,
    }
