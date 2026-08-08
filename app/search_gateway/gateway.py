from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.search_gateway.cache import MemorySearchCache
from app.search_gateway.models import (
    AttemptState,
    FallbackReason,
    GatewayState,
    ProviderAttempt,
    ProviderHealth,
    ProviderReadiness,
    SearchDiagnostics,
    SearchItem,
    SearchPolicy,
    SearchRequest,
    SearchResponse,
)
from app.search_gateway.providers import ProviderError, SearchProvider


TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "yclid",
    "_openstat",
}

HARD_UPSTREAM_FAILURES = {
    FallbackReason.RATE_LIMITED,
    FallbackReason.PROVIDER_BLOCKED,
    FallbackReason.CAPTCHA,
}


def canonical_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    port = parsed.port
    netloc = host
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    query = urlencode(
        sorted(
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith("utm_") and key.lower() not in TRACKING_QUERY_KEYS
        )
    )
    return urlunsplit((scheme, netloc, path, query, ""))


def request_fingerprint(request: SearchRequest) -> str:
    payload = {
        "query": " ".join(request.query.split()).casefold(),
        "limit": request.limit,
        "language": request.language.casefold(),
    }
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return f"sha256:{digest}"


@dataclass
class _Circuit:
    failures: int = 0
    opened_at: float | None = None


class SearchGateway:
    def __init__(
        self,
        providers: list[SearchProvider],
        *,
        cache: MemorySearchCache | None = None,
        failure_threshold: int = 3,
        recovery_seconds: float = 60.0,
        global_quotas: dict[str, int] | None = None,
    ) -> None:
        self._providers = {provider.name: provider for provider in providers}
        self._cache = cache or MemorySearchCache()
        self._failure_threshold = failure_threshold
        self._recovery_seconds = recovery_seconds
        self._circuits = {name: _Circuit() for name in self._providers}
        self._global_quotas = dict(global_quotas or {})
        self._global_usage = {name: 0 for name in self._providers}
        self._mission_costs: dict[str, dict[str, Decimal]] = {}
        self._lock = asyncio.Lock()

    def _circuit_state(self, provider: str) -> str:
        circuit = self._circuits[provider]
        if circuit.opened_at is None:
            return "closed"
        if time.monotonic() - circuit.opened_at >= self._recovery_seconds:
            return "half_open"
        return "open"

    async def _record_success(self, provider: str) -> None:
        async with self._lock:
            self._circuits[provider] = _Circuit()

    async def _record_failure(
        self,
        provider: str,
        reason: FallbackReason = FallbackReason.PROVIDER_ERROR,
    ) -> None:
        async with self._lock:
            circuit = self._circuits[provider]
            circuit.failures += 1
            if reason in HARD_UPSTREAM_FAILURES or circuit.failures >= self._failure_threshold:
                circuit.opened_at = time.monotonic()

    async def _reserve_cost(
        self,
        request: SearchRequest,
        provider: SearchProvider,
        policy: SearchPolicy,
        *,
        fallback: bool,
    ) -> FallbackReason | None:
        if provider.paid and fallback and not policy.allow_paid_fallback:
            return FallbackReason.POLICY_BLOCKED
        if provider.paid and provider.cost_amount <= 0:
            return FallbackReason.PRICING_UNKNOWN
        async with self._lock:
            quota = self._global_quotas.get(provider.name)
            if quota is not None and self._global_usage[provider.name] >= quota:
                return FallbackReason.QUOTA_BLOCKED
            costs = self._mission_costs.setdefault(request.mission_id, {})
            current = costs.get(provider.cost_currency, Decimal("0"))
            maximum = policy.max_cost_by_currency.get(provider.cost_currency)
            if provider.cost_amount > 0 and (maximum is None or current + provider.cost_amount > maximum):
                return FallbackReason.BUDGET_BLOCKED
            self._global_usage[provider.name] += 1
            costs[provider.cost_currency] = current + provider.cost_amount
        return None

    @staticmethod
    def _dedupe(results: list[SearchItem], limit: int) -> list[SearchItem]:
        unique: dict[str, SearchItem] = {}
        for item in results:
            normalized = canonical_url(str(item.url))
            if not normalized or normalized in unique:
                continue
            unique[normalized] = item.model_copy(update={"url": normalized})
            if len(unique) >= limit:
                break
        return list(unique.values())

    async def search(
        self,
        request: SearchRequest,
        policy: SearchPolicy | None = None,
    ) -> SearchResponse:
        policy = policy or SearchPolicy()
        fingerprint = request_fingerprint(request)
        cache_key = fingerprint
        cached = await self._cache.get(cache_key)
        if cached is not None:
            attempt = ProviderAttempt(
                provider="cache",
                state=AttemptState.CACHE_HIT,
                request_fingerprint=fingerprint,
                latency_ms=0,
                result_count=len(cached),
            )
            return SearchResponse(
                results=cached[: request.limit],
                diagnostics=SearchDiagnostics(
                    state=GatewayState.SUCCESS,
                    selected_provider="cache",
                    cache_hit=True,
                    attempts=[attempt],
                ),
            )

        attempts: list[ProviderAttempt] = []
        executed = 0
        for provider_name in policy.provider_order:
            provider = self._providers.get(provider_name)
            policy_blocked = (
                policy.allowed_providers is not None
                and provider_name not in policy.allowed_providers
            )
            if provider is None or policy_blocked or not provider.configured:
                reason = (
                    FallbackReason.POLICY_BLOCKED
                    if policy_blocked
                    else FallbackReason.NOT_CONFIGURED
                )
                attempts.append(
                    ProviderAttempt(
                        provider=provider_name,
                        state=AttemptState.SKIPPED,
                        request_fingerprint=fingerprint,
                        latency_ms=0,
                        result_count=0,
                        reason=reason,
                    )
                )
                continue
            if self._circuit_state(provider_name) == "open":
                attempts.append(
                    ProviderAttempt(
                        provider=provider_name,
                        state=AttemptState.SKIPPED,
                        request_fingerprint=fingerprint,
                        latency_ms=0,
                        result_count=0,
                        reason=FallbackReason.CIRCUIT_OPEN,
                    )
                )
                continue
            blocked = await self._reserve_cost(
                request,
                provider,
                policy,
                fallback=executed > 0,
            )
            if blocked:
                attempts.append(
                    ProviderAttempt(
                        provider=provider_name,
                        state=AttemptState.SKIPPED,
                        request_fingerprint=fingerprint,
                        latency_ms=0,
                        result_count=0,
                        reason=blocked,
                        cost_currency=provider.cost_currency,
                    )
                )
                continue

            executed += 1
            started = time.perf_counter()
            error_reason: FallbackReason | None = None
            results: list[SearchItem] = []
            calls_made = 0
            for retry in range(policy.retries + 1):
                if retry > 0:
                    retry_blocked = await self._reserve_cost(
                        request,
                        provider,
                        policy,
                        fallback=executed > 1,
                    )
                    if retry_blocked:
                        error_reason = retry_blocked
                        break
                try:
                    calls_made += 1
                    results = await provider.search(
                        request,
                        timeout_seconds=policy.timeout_seconds,
                    )
                    error_reason = None
                    break
                except ProviderError as exc:
                    error_reason = exc.reason
                    if not exc.retryable or retry >= policy.retries:
                        break
                except Exception:
                    error_reason = FallbackReason.PROVIDER_ERROR
                    break
            latency_ms = max(0, round((time.perf_counter() - started) * 1000))
            charged = provider.cost_amount * calls_made
            if error_reason is not None:
                await self._record_failure(provider_name, error_reason)
                attempts.append(
                    ProviderAttempt(
                        provider=provider_name,
                        state=AttemptState.FAILED,
                        request_fingerprint=fingerprint,
                        latency_ms=latency_ms,
                        result_count=0,
                        reason=error_reason,
                        cost_amount=charged,
                        cost_currency=provider.cost_currency,
                    )
                )
                continue

            await self._record_success(provider_name)
            results = self._dedupe(results, request.limit)
            state = AttemptState.SUCCEEDED if results else AttemptState.EMPTY
            attempts.append(
                ProviderAttempt(
                    provider=provider_name,
                    state=state,
                    request_fingerprint=fingerprint,
                    latency_ms=latency_ms,
                    result_count=len(results),
                    reason=None if results else FallbackReason.EMPTY_RESULTS,
                    cost_amount=charged,
                    cost_currency=provider.cost_currency,
                )
            )
            if results:
                await self._cache.set(cache_key, results, policy.cache_ttl_seconds)
                totals: dict[str, Decimal] = {}
                for attempt in attempts:
                    if attempt.state in {AttemptState.SUCCEEDED, AttemptState.EMPTY, AttemptState.FAILED}:
                        totals[attempt.cost_currency] = (
                            totals.get(attempt.cost_currency, Decimal("0")) + attempt.cost_amount
                        )
                return SearchResponse(
                    results=results,
                    diagnostics=SearchDiagnostics(
                        state=GatewayState.DEGRADED if executed > 1 else GatewayState.SUCCESS,
                        selected_provider=provider_name,
                        fallback_used=executed > 1,
                        attempts=attempts,
                        total_cost_by_currency=totals,
                    ),
                )

        state = GatewayState.DEGRADED if executed else GatewayState.UNAVAILABLE
        totals: dict[str, Decimal] = {}
        for attempt in attempts:
            if attempt.cost_amount:
                totals[attempt.cost_currency] = (
                    totals.get(attempt.cost_currency, Decimal("0")) + attempt.cost_amount
                )
        return SearchResponse(
            results=[],
            diagnostics=SearchDiagnostics(
                state=state,
                selected_provider=None,
                fallback_used=executed > 1,
                attempts=attempts,
                total_cost_by_currency=totals,
            ),
        )

    def health(self, policy: SearchPolicy | None = None) -> list[ProviderHealth]:
        policy = policy or SearchPolicy()
        health: list[ProviderHealth] = []
        for name, provider in self._providers.items():
            quota = self._global_quotas.get(name)
            remaining = None if quota is None else max(0, quota - self._global_usage[name])
            circuit_state = self._circuit_state(name)
            maximum = policy.max_cost_by_currency.get(provider.cost_currency)
            if not provider.configured:
                state = ProviderReadiness.NOT_CONFIGURED
            elif circuit_state == "open":
                state = ProviderReadiness.CIRCUIT_OPEN
            elif remaining == 0:
                state = ProviderReadiness.QUOTA_BLOCKED
            elif provider.paid and provider.cost_amount <= 0:
                state = ProviderReadiness.PRICING_UNKNOWN
            elif provider.paid and (
                maximum is None or maximum < provider.cost_amount
            ):
                state = ProviderReadiness.BUDGET_BLOCKED
            else:
                state = ProviderReadiness.ACTIVE
            health.append(
                ProviderHealth(
                    provider=name,
                    state=state,
                    ready=state == ProviderReadiness.ACTIVE,
                    configured=provider.configured,
                    paid=provider.paid,
                    circuit_state=circuit_state,
                    quota_remaining=remaining,
                )
            )
        return health
