from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field


class GatewayModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GatewayState(StrEnum):
    SUCCESS = "success"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class AttemptState(StrEnum):
    SUCCEEDED = "succeeded"
    EMPTY = "empty"
    FAILED = "failed"
    SKIPPED = "skipped"
    CACHE_HIT = "cache_hit"


class ProviderReadiness(StrEnum):
    ACTIVE = "active"
    NOT_CONFIGURED = "not_configured"
    POLICY_BLOCKED = "policy_blocked"
    CONTRACT_BLOCKED = "contract_blocked"
    PRICING_UNKNOWN = "pricing_unknown"
    BUDGET_BLOCKED = "budget_blocked"
    QUOTA_BLOCKED = "quota_blocked"
    CIRCUIT_OPEN = "circuit_open"


class FallbackReason(StrEnum):
    NOT_CONFIGURED = "not_configured"
    POLICY_BLOCKED = "policy_blocked"
    CONTRACT_BLOCKED = "contract_blocked"
    PRICING_UNKNOWN = "pricing_unknown"
    BUDGET_BLOCKED = "budget_blocked"
    QUOTA_BLOCKED = "quota_blocked"
    BUDGET_EXCEEDED = "budget_exceeded"
    QUOTA_EXCEEDED = "quota_exceeded"
    CIRCUIT_OPEN = "circuit_open"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    PROVIDER_BLOCKED = "provider_blocked"
    CAPTCHA = "captcha"
    PROTOCOL_ERROR = "protocol_error"
    PROVIDER_ERROR = "provider_error"
    EMPTY_RESULTS = "empty_results"


class SearchStrategy(StrEnum):
    PRIMARY_ONLY = "primary_only"
    FALLBACK_FIRST_NONEMPTY = "fallback_first_nonempty"
    CASCADE_UNTIL_TARGET = "cascade_until_target"
    SEQUENTIAL_UNION = "sequential_union"
    PARALLEL_UNION = "parallel_union"
    CONSENSUS_UNION = "consensus_union"
    SPLIT_QUERY_ROUTING = "split_query_routing"
    ADAPTIVE_COST_QUALITY = "adaptive_cost_quality"
    EXHAUSTIVE_COVERAGE = "exhaustive_coverage"
    SHADOW_COMPARE = "shadow_compare"


class SearchItem(GatewayModel):
    url: AnyHttpUrl
    title: str = Field(default="", max_length=1000)
    snippet: str = Field(default="", max_length=4000)
    published_at: str | None = Field(default=None, max_length=100)
    provider: str = Field(min_length=1, max_length=100)
    corroborated_by: list[str] = Field(default_factory=list, max_length=16)

    def as_legacy_dict(self) -> dict[str, str]:
        payload = {
            "url": str(self.url),
            "title": self.title,
            "content": self.snippet,
            "provider": self.provider,
        }
        if self.published_at:
            payload["publishedDate"] = self.published_at
        return payload


class SearchRequest(GatewayModel):
    query: str = Field(min_length=1, max_length=400)
    limit: int = Field(default=10, ge=1, le=100)
    language: str = Field(default="ru-RU", min_length=2, max_length=20)
    mission_id: str = Field(min_length=1, max_length=200)
    correlation_id: str = Field(min_length=1, max_length=200)


class SearchPolicy(GatewayModel):
    provider_order: tuple[str, ...] = ("yandex", "searxng", "tavily")
    allowed_providers: frozenset[str] | None = None
    strategy: SearchStrategy = SearchStrategy.FALLBACK_FIRST_NONEMPTY
    target_results: int = Field(default=10, ge=1, le=100)
    max_providers_per_query: int = Field(default=3, ge=1, le=16)
    allow_paid_fallback: bool = False
    allow_paid_fanout: bool = False
    max_cost_by_currency: dict[str, Decimal] = Field(default_factory=dict)
    timeout_seconds: float = Field(default=15.0, ge=0.1, le=120)
    retries: int = Field(default=1, ge=0, le=3)
    retry_backoff_base_seconds: float = Field(default=0.5, ge=0.0, le=30.0)
    retry_backoff_max_seconds: float = Field(default=4.0, ge=0.0, le=120.0)
    cache_ttl_seconds: int = Field(default=900, ge=0, le=86400)


class ProviderAttempt(GatewayModel):
    provider: str
    state: AttemptState
    request_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    latency_ms: int = Field(ge=0)
    result_count: int = Field(ge=0)
    reason: FallbackReason | None = None
    degraded_upstreams: list[str] = Field(default_factory=list, max_length=16)
    cost_amount: Decimal = Field(default=Decimal("0"), ge=0)
    cost_currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")


class SearchDiagnostics(GatewayModel):
    state: GatewayState
    selected_provider: str | None = None
    cache_hit: bool = False
    coalesced: bool = False
    fallback_used: bool = False
    attempts: list[ProviderAttempt] = Field(default_factory=list)
    total_cost_by_currency: dict[str, Decimal] = Field(default_factory=dict)

    @classmethod
    def aggregate(cls, diagnostics: list[SearchDiagnostics]) -> SearchDiagnostics:
        attempts = [attempt for item in diagnostics for attempt in item.attempts]
        totals: dict[str, Decimal] = {}
        for item in diagnostics:
            for currency, amount in item.total_cost_by_currency.items():
                totals[currency] = totals.get(currency, Decimal("0")) + amount
        if not diagnostics or all(item.state == GatewayState.UNAVAILABLE for item in diagnostics):
            state = GatewayState.UNAVAILABLE
        elif any(item.state != GatewayState.SUCCESS for item in diagnostics):
            state = GatewayState.DEGRADED
        else:
            state = GatewayState.SUCCESS
        selected = next((item.selected_provider for item in diagnostics if item.selected_provider), None)
        return cls(
            state=state,
            selected_provider=selected,
            cache_hit=any(item.cache_hit for item in diagnostics),
            coalesced=any(item.coalesced for item in diagnostics),
            fallback_used=any(item.fallback_used for item in diagnostics),
            attempts=attempts,
            total_cost_by_currency=totals,
        )


class SearchResponse(GatewayModel):
    results: list[SearchItem]
    diagnostics: SearchDiagnostics


class UpstreamCooldown(GatewayModel):
    upstream: str = Field(min_length=1, max_length=100)
    reason: FallbackReason
    retry_after_seconds: int = Field(ge=0, le=2592000)


class ProviderScheduling(GatewayModel):
    max_concurrency: int = Field(ge=1, le=64)
    jitter_min_seconds: float = Field(ge=0.0, le=30.0)
    jitter_max_seconds: float = Field(ge=0.0, le=30.0)


class ProviderHealth(GatewayModel):
    provider: str
    state: ProviderReadiness
    ready: bool
    configured: bool
    paid: bool
    circuit_state: Literal["closed", "open", "half_open"]
    quota_remaining: int | None = Field(default=None, ge=0)
    upstream_cooldowns: list[UpstreamCooldown] | None = None
    scheduling: ProviderScheduling | None = None
