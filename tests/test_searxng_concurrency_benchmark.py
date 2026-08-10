from __future__ import annotations

import pytest

from scripts.benchmark_searxng_concurrency import (
    BENCHMARK_QUERIES,
    CONCURRENCY_MATRIX,
    build_plan,
    require_live_authorization,
    result_precision_proxy,
    summarize_records,
)


def test_dry_run_plan_is_fixed_and_zero_call() -> None:
    plan = build_plan(engine_fanout=2)

    assert plan["matrix"] == [1, 2, 3, 6]
    assert plan["query_count_per_concurrency"] == 6
    assert plan["planned_searxng_calls"] == 24
    assert plan["planned_upstream_engine_invocations_ceiling"] == 48
    assert plan["external_provider_calls"] == 0
    assert plan["live_calls_authorized"] is False
    assert "precision_proxy" in plan["metrics"]


def test_query_fixture_is_stable_unique_and_bounded() -> None:
    assert CONCURRENCY_MATRIX == (1, 2, 3, 6)
    assert len(BENCHMARK_QUERIES) == 6
    assert len(set(BENCHMARK_QUERIES)) == len(BENCHMARK_QUERIES)
    assert all("Красноярск" in query for query in BENCHMARK_QUERIES)


def test_precision_proxy_is_transparent_two_signal_score() -> None:
    assert (
        result_precision_proxy(
            "https://clinic.example/krasnoyarsk",
            "Стоматология Красноярск",
            "Имплантация и лечение зубов",
        )
        == 1.0
    )
    assert result_precision_proxy("https://dental.example/", "Dental clinic", "services") == 0.5
    assert result_precision_proxy("https://example.org/", "Новости", "Обзор рынка") == 0.0


def test_summary_reports_success_latency_block_and_precision() -> None:
    records = [
        {
            "latency_seconds": 1.0,
            "result_count": 2,
            "reason": None,
            "degraded_upstreams": [],
            "precision_scores": [1.0, 0.5],
        },
        {
            "latency_seconds": 2.0,
            "result_count": 1,
            "reason": "captcha",
            "degraded_upstreams": ["duckduckgo"],
            "precision_scores": [0.5],
        },
        {
            "latency_seconds": 3.0,
            "result_count": 0,
            "reason": "circuit_open",
            "degraded_upstreams": [],
            "precision_scores": [],
        },
    ]

    summary = summarize_records(records, concurrency=3)

    assert summary["concurrency"] == 3
    assert summary["success_rate"] == 0.6667
    assert summary["latency_p50_seconds"] == 2.0
    assert summary["latency_p95_seconds"] == 3.0
    assert summary["block_or_degradation_rate"] == 0.6667
    assert summary["result_count"] == 3
    assert summary["precision_proxy"] == 0.6667


def test_live_mode_requires_explicit_authorization() -> None:
    with pytest.raises(SystemExit, match="explicit owner authorization"):
        require_live_authorization(live=True, allow_live_calls=False)

    require_live_authorization(live=False, allow_live_calls=False)
    require_live_authorization(live=True, allow_live_calls=True)
