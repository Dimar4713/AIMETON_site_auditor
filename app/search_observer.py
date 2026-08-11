from __future__ import annotations

from collections import Counter
from decimal import Decimal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from app.search_gateway import SearchResponse


class ObserverModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QueryYieldTelemetry(ObserverModel):
    query: str = Field(min_length=1, max_length=400)
    result_count: int = Field(ge=0)
    unique_domain_count: int = Field(ge=0)
    duplicate_domain_ratio: float = Field(ge=0.0, le=1.0)
    provider_result_counts: dict[str, int] = Field(default_factory=dict)
    attempt_states: dict[str, int] = Field(default_factory=dict)
    latency_ms_total: int = Field(ge=0)
    degraded_attempts: int = Field(ge=0)
    cache_hit: bool = False
    total_cost_by_currency: dict[str, Decimal] = Field(default_factory=dict)


class SearchWaveTelemetry(ObserverModel):
    query_count: int = Field(ge=0)
    result_count: int = Field(ge=0)
    unique_domain_count: int = Field(ge=0)
    duplicate_domain_ratio: float = Field(ge=0.0, le=1.0)
    provider_result_counts: dict[str, int] = Field(default_factory=dict)
    attempt_states: dict[str, int] = Field(default_factory=dict)
    latency_ms_total: int = Field(ge=0)
    degraded_attempts: int = Field(ge=0)
    total_cost_by_currency: dict[str, Decimal] = Field(default_factory=dict)
    directions: list[QueryYieldTelemetry] = Field(default_factory=list)


def _domain(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def _duplicate_ratio(values: list[str]) -> float:
    usable = [value for value in values if value]
    if not usable:
        return 0.0
    return round(1.0 - (len(set(usable)) / len(usable)), 6)


def build_search_wave_telemetry(
    queries: list[str],
    responses: list[SearchResponse],
) -> SearchWaveTelemetry:
    """Build observer input from completed search work without changing routing.

    This is Phase A telemetry only. It has no execution capability and does not
    alter provider selection, concurrency, retries, circuits, budgets or query order.
    """
    directions: list[QueryYieldTelemetry] = []
    wave_provider_counts: Counter[str] = Counter()
    wave_attempt_states: Counter[str] = Counter()
    wave_domains: list[str] = []
    wave_latency = 0
    wave_degraded = 0
    wave_costs: dict[str, Decimal] = {}

    for query, response in zip(queries, responses, strict=True):
        domains = [_domain(str(item.url)) for item in response.results]
        provider_counts = Counter(item.provider for item in response.results)
        attempt_states = Counter(str(attempt.state) for attempt in response.diagnostics.attempts)
        latency_total = sum(attempt.latency_ms for attempt in response.diagnostics.attempts)
        degraded_attempts = sum(
            1
            for attempt in response.diagnostics.attempts
            if str(attempt.state) == "failed" or attempt.reason is not None
        )

        directions.append(
            QueryYieldTelemetry(
                query=query,
                result_count=len(response.results),
                unique_domain_count=len({domain for domain in domains if domain}),
                duplicate_domain_ratio=_duplicate_ratio(domains),
                provider_result_counts=dict(provider_counts),
                attempt_states=dict(attempt_states),
                latency_ms_total=latency_total,
                degraded_attempts=degraded_attempts,
                cache_hit=response.diagnostics.cache_hit,
                total_cost_by_currency=response.diagnostics.total_cost_by_currency,
            )
        )

        wave_domains.extend(domains)
        wave_provider_counts.update(provider_counts)
        wave_attempt_states.update(attempt_states)
        wave_latency += latency_total
        wave_degraded += degraded_attempts
        for currency, amount in response.diagnostics.total_cost_by_currency.items():
            wave_costs[currency] = wave_costs.get(currency, Decimal("0")) + amount

    return SearchWaveTelemetry(
        query_count=len(directions),
        result_count=sum(item.result_count for item in directions),
        unique_domain_count=len({domain for domain in wave_domains if domain}),
        duplicate_domain_ratio=_duplicate_ratio(wave_domains),
        provider_result_counts=dict(wave_provider_counts),
        attempt_states=dict(wave_attempt_states),
        latency_ms_total=wave_latency,
        degraded_attempts=wave_degraded,
        total_cost_by_currency=wave_costs,
        directions=directions,
    )
