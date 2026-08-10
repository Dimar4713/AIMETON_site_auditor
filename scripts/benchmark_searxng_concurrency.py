from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import statistics
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any


CONCURRENCY_MATRIX = (1, 2, 3, 6)
DEFAULT_ENGINE_FANOUT = 2
DEFAULT_RESULT_LIMIT = 10
DEFAULT_TIMEOUT_SECONDS = 30.0
BENCHMARK_QUERIES = (
    "стоматология Красноярск официальный сайт",
    "имплантация зубов Красноярск клиника",
    "ортодонт брекеты Красноярск стоматология",
    "детская стоматология Красноярск",
    "протезирование зубов Красноярск стоматология",
    "лечение кариеса Красноярск стоматология",
)
INDUSTRY_MARKERS = (
    "стомат",
    "зуб",
    "дент",
    "dental",
    "dent",
    "имплант",
    "ортодонт",
    "брекет",
)
REGION_MARKERS = (
    "красноярск",
    "красноярский",
)
BLOCK_REASONS = frozenset(
    {
        "captcha",
        "rate_limited",
        "provider_blocked",
        "protocol_error",
        "circuit_open",
    }
)
NON_CALL_STATES = frozenset({"skipped", "cache_hit"})


def _env_int(name: str, default: int, *, minimum: int = 1, maximum: int = 64) -> int:
    try:
        value = int((os.getenv(name) or str(default)).strip())
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def _env_float(
    name: str,
    default: float,
    *,
    minimum: float = 0.0,
    maximum: float = 120.0,
) -> float:
    try:
        value = float((os.getenv(name) or str(default)).strip())
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def _csv_env(name: str, default: Sequence[str]) -> tuple[str, ...]:
    raw = os.getenv(name)
    if raw is None:
        return tuple(default)
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def build_plan(
    *,
    query_count: int = len(BENCHMARK_QUERIES),
    engine_fanout: int = DEFAULT_ENGINE_FANOUT,
) -> dict[str, Any]:
    searxng_calls = query_count * len(CONCURRENCY_MATRIX)
    return {
        "mode": "dry_run",
        "matrix": list(CONCURRENCY_MATRIX),
        "query_count_per_concurrency": query_count,
        "planned_searxng_calls": searxng_calls,
        "engine_fanout": engine_fanout,
        "planned_upstream_engine_invocations_ceiling": searxng_calls * engine_fanout,
        "metrics": [
            "success_rate",
            "latency_p50_seconds",
            "latency_p95_seconds",
            "block_or_degradation_rate",
            "precision_proxy",
            "provider_calls",
        ],
        "precision_proxy_definition": (
            "mean per-result score: 0.5 for dentistry signal + 0.5 for Krasnoyarsk signal; "
            "deterministic comparison proxy, not human-adjudicated precision"
        ),
        "live_calls_authorized": False,
        "external_provider_calls": 0,
    }


def result_precision_proxy(url: str, title: str, snippet: str) -> float:
    text = " ".join((url, title, snippet)).casefold()
    industry = any(marker in text for marker in INDUSTRY_MARKERS)
    region = any(marker in text for marker in REGION_MARKERS)
    return (0.5 if industry else 0.0) + (0.5 if region else 0.0)


def _nearest_rank_percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    rank = max(1, math.ceil(quantile * len(ordered)))
    return ordered[rank - 1]


def summarize_records(
    records: Sequence[dict[str, Any]],
    *,
    concurrency: int,
) -> dict[str, Any]:
    query_count = len(records)
    successful = sum(1 for row in records if int(row["result_count"]) > 0)
    degraded = sum(
        1
        for row in records
        if row.get("reason") in BLOCK_REASONS or bool(row.get("degraded_upstreams"))
    )
    latencies = [float(row["latency_seconds"]) for row in records]
    precision_values = [
        float(score)
        for row in records
        for score in row.get("precision_scores", [])
    ]
    return {
        "concurrency": concurrency,
        "query_count": query_count,
        "provider_calls": sum(1 for row in records if bool(row.get("provider_called"))),
        "successful_queries": successful,
        "success_rate": round(successful / query_count, 4) if query_count else 0.0,
        "latency_p50_seconds": round(statistics.median(latencies), 4) if latencies else 0.0,
        "latency_p95_seconds": round(_nearest_rank_percentile(latencies, 0.95), 4),
        "latency_max_seconds": round(max(latencies), 4) if latencies else 0.0,
        "blocked_or_degraded_queries": degraded,
        "block_or_degradation_rate": round(degraded / query_count, 4) if query_count else 0.0,
        "result_count": sum(int(row["result_count"]) for row in records),
        "precision_proxy": round(statistics.fmean(precision_values), 4) if precision_values else 0.0,
    }


def require_live_authorization(*, live: bool, allow_live_calls: bool) -> None:
    if live and not allow_live_calls:
        raise SystemExit(
            "Refusing live SearXNG benchmark: pass --allow-live-calls only after explicit owner authorization."
        )


async def _run_live_query(
    gateway: Any,
    policy: Any,
    *,
    query: str,
    index: int,
    result_limit: int,
) -> dict[str, Any]:
    from app.search_gateway.models import SearchRequest

    request = SearchRequest(
        query=query,
        limit=result_limit,
        language="ru-RU",
        mission_id="benchmark-searxng-concurrency-stage",
        correlation_id=f"benchmark-searxng-{index}-{time.time_ns()}",
    )
    started = time.monotonic()
    response = await gateway.search(request, policy)
    latency = time.monotonic() - started
    attempt = next(
        (item for item in reversed(response.diagnostics.attempts) if item.provider == "searxng"),
        None,
    )
    return {
        "query_index": index,
        "latency_seconds": latency,
        "result_count": len(response.results),
        "provider_called": bool(attempt and attempt.state.value not in NON_CALL_STATES),
        "attempt_state": attempt.state.value if attempt else None,
        "reason": attempt.reason.value if attempt and attempt.reason else None,
        "degraded_upstreams": list(attempt.degraded_upstreams) if attempt else [],
        "precision_scores": [
            result_precision_proxy(str(item.url), item.title, item.snippet)
            for item in response.results
        ],
    }


async def _run_concurrency(
    *,
    base_url: str,
    engines: tuple[str, ...],
    engine_fanout: int,
    concurrency: int,
    result_limit: int,
    timeout_seconds: float,
    jitter_min_seconds: float,
    jitter_max_seconds: float,
) -> dict[str, Any]:
    from app.search_gateway.gateway import SearchGateway
    from app.search_gateway.models import SearchPolicy
    from app.search_gateway.providers import SearxngProvider
    from app.search_gateway.scheduler import ScheduledProvider

    provider = ScheduledProvider(
        SearxngProvider(
            base_url,
            engines=engines,
            engine_fanout=engine_fanout,
        ),
        max_concurrency=concurrency,
        jitter_min_seconds=jitter_min_seconds,
        jitter_max_seconds=jitter_max_seconds,
    )
    gateway = SearchGateway([provider])
    policy = SearchPolicy(
        provider_order=("searxng",),
        allowed_providers=frozenset({"searxng"}),
        timeout_seconds=timeout_seconds,
        retries=0,
        cache_ttl_seconds=0,
    )
    records = await asyncio.gather(
        *(
            _run_live_query(
                gateway,
                policy,
                query=query,
                index=index,
                result_limit=result_limit,
            )
            for index, query in enumerate(BENCHMARK_QUERIES, start=1)
        )
    )
    return summarize_records(records, concurrency=concurrency)


async def run_live_benchmark() -> dict[str, Any]:
    base_url = (os.getenv("SEARXNG_BASE_URL") or "").strip().rstrip("/")
    if not base_url:
        raise SystemExit("SEARXNG_BASE_URL is not configured")
    engines = _csv_env(
        "SEARXNG_ENGINES",
        ("brave", "duckduckgo", "google cse", "startpage", "bing"),
    )
    if not engines:
        raise SystemExit("SEARXNG_ENGINES resolved to an empty engine pool")
    engine_fanout = _env_int("SEARXNG_ENGINES_PER_REQUEST", DEFAULT_ENGINE_FANOUT)
    result_limit = _env_int("SEARXNG_BENCHMARK_RESULT_LIMIT", DEFAULT_RESULT_LIMIT, maximum=20)
    timeout_seconds = _env_float(
        "SEARCH_TIMEOUT_SECONDS",
        DEFAULT_TIMEOUT_SECONDS,
        minimum=1.0,
        maximum=120.0,
    )
    jitter_min = _env_float("SEARCH_JITTER_SEARXNG_MIN_SECONDS", 0.2, maximum=30.0)
    jitter_max = _env_float("SEARCH_JITTER_SEARXNG_MAX_SECONDS", 0.8, maximum=30.0)
    if jitter_max < jitter_min:
        jitter_max = jitter_min

    rows: list[dict[str, Any]] = []
    for concurrency in CONCURRENCY_MATRIX:
        rows.append(
            await _run_concurrency(
                base_url=base_url,
                engines=engines,
                engine_fanout=engine_fanout,
                concurrency=concurrency,
                result_limit=result_limit,
                timeout_seconds=timeout_seconds,
                jitter_min_seconds=jitter_min,
                jitter_max_seconds=jitter_max,
            )
        )

    return {
        "mode": "live",
        "deployed_sha": os.getenv("BENCHMARK_DEPLOYED_SHA"),
        "matrix": list(CONCURRENCY_MATRIX),
        "query_count_per_concurrency": len(BENCHMARK_QUERIES),
        "planned_searxng_calls": len(BENCHMARK_QUERIES) * len(CONCURRENCY_MATRIX),
        "actual_searxng_provider_calls": sum(int(row["provider_calls"]) for row in rows),
        "engine_pool": list(engines),
        "engine_fanout": engine_fanout,
        "jitter_seconds": {"min": jitter_min, "max": jitter_max},
        "precision_proxy_definition": build_plan(engine_fanout=engine_fanout)[
            "precision_proxy_definition"
        ],
        "results": rows,
        "live_calls_authorized": True,
    }


def _write_output(payload: dict[str, Any], path: str | None) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    print(rendered)
    if path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered + "\n", encoding="utf-8")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIMETON SearXNG concurrency benchmark")
    parser.add_argument("--live", action="store_true", help="Execute real SearXNG calls")
    parser.add_argument(
        "--allow-live-calls",
        action="store_true",
        help="Explicit owner authorization gate required together with --live",
    )
    parser.add_argument("--output", help="Optional JSON output path")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    require_live_authorization(live=args.live, allow_live_calls=args.allow_live_calls)
    if not args.live:
        engine_fanout = _env_int("SEARXNG_ENGINES_PER_REQUEST", DEFAULT_ENGINE_FANOUT)
        _write_output(build_plan(engine_fanout=engine_fanout), args.output)
        return 0
    payload = asyncio.run(run_live_benchmark())
    _write_output(payload, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
