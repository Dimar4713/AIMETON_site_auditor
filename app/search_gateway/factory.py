from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation
from functools import lru_cache

from app.search_gateway.cache import SQLiteSearchCache, SearchCache
from app.search_gateway.factory_helpers import first_nonempty_env
from app.search_gateway.models import SearchPolicy, SearchStrategy
from app.search_gateway.providers import TavilyProvider, YandexProvider
from app.search_gateway.upstream_telemetry import (
    ScheduledProvider,
    SearxngProvider,
    TracedSearchGateway,
)


DEBUG_BUDGET_CEILING = Decimal("999999")
DEFAULT_SEARXNG_ENGINES = (
    "brave",
    "duckduckgo",
    "google cse",
    "startpage",
    "bing",
)


def _decimal_env(name: str, default: str = "0") -> Decimal:
    try:
        return Decimal(os.getenv(name, default).strip() or default)
    except InvalidOperation:
        return Decimal("0")


def _quota_env(name: str) -> int | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        return max(0, int(raw))
    except ValueError:
        return None


def _int_env(name: str, default: int, *, minimum: int = 1, maximum: int = 64) -> int:
    try:
        value = int(os.getenv(name, str(default)).strip())
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def _float_env(name: str, default: float, *, minimum: float = 0.0, maximum: float = 30.0) -> float:
    try:
        value = float(os.getenv(name, str(default)).strip())
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _csv_env(name: str, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    raw = os.getenv(name)
    if raw is None:
        return default
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _strategy_env(name: str, default: SearchStrategy) -> SearchStrategy:
    raw = os.getenv(name, str(default)).strip()
    try:
        return SearchStrategy(raw)
    except ValueError:
        return default


def _scheduled(
    provider,
    *,
    concurrency_env: str,
    concurrency_default: int,
    jitter_min_env: str,
    jitter_min_default: float,
    jitter_max_env: str,
    jitter_max_default: float,
) -> ScheduledProvider:
    jitter_min = _float_env(jitter_min_env, jitter_min_default)
    jitter_max = _float_env(jitter_max_env, jitter_max_default)
    if jitter_max < jitter_min:
        jitter_max = jitter_min
    return ScheduledProvider(
        provider,
        max_concurrency=_int_env(concurrency_env, concurrency_default),
        jitter_min_seconds=jitter_min,
        jitter_max_seconds=jitter_max,
    )


def search_effectiveness_debug_enabled() -> bool:
    return _bool_env("SEARCH_EFFECTIVENESS_DEBUG")


def search_policy_from_env() -> SearchPolicy:
    order = tuple(
        item.strip()
        for item in os.getenv("SEARCH_PROVIDER_ORDER", "yandex,searxng,tavily").split(",")
        if item.strip()
    )
    debug = search_effectiveness_debug_enabled()
    if debug:
        budgets = {"RUB": DEBUG_BUDGET_CEILING, "USD": DEBUG_BUDGET_CEILING}
    else:
        budgets = {
            currency: amount
            for currency, amount in {
                "RUB": _decimal_env("SEARCH_MISSION_BUDGET_RUB"),
                "USD": _decimal_env("SEARCH_MISSION_BUDGET_USD"),
            }.items()
            if amount > 0
        }
    return SearchPolicy(
        provider_order=order,
        allowed_providers=frozenset(order),
        strategy=_strategy_env("SEARCH_STRATEGY", SearchStrategy.FALLBACK_FIRST_NONEMPTY),
        target_results=_int_env("SEARCH_TARGET_RESULTS", 10, minimum=1, maximum=100),
        max_providers_per_query=_int_env("SEARCH_MAX_PROVIDERS_PER_QUERY", 3, minimum=1, maximum=16),
        allow_paid_fallback=True if debug else _bool_env("SEARCH_ALLOW_PAID_FALLBACK"),
        allow_paid_fanout=True if debug else _bool_env("SEARCH_ALLOW_PAID_FANOUT"),
        max_cost_by_currency=budgets,
        timeout_seconds=float(os.getenv("SEARCH_TIMEOUT_SECONDS", "15")),
        retries=int(os.getenv("SEARCH_RETRIES", "1")),
        retry_backoff_base_seconds=_float_env(
            "SEARCH_RETRY_BACKOFF_BASE_SECONDS", 0.5, minimum=0.0, maximum=30.0
        ),
        retry_backoff_max_seconds=_float_env(
            "SEARCH_RETRY_BACKOFF_MAX_SECONDS", 4.0, minimum=0.0, maximum=120.0
        ),
        cache_ttl_seconds=int(os.getenv("SEARCH_CACHE_TTL_SECONDS", "900")),
    )


def identity_search_policy_from_env() -> SearchPolicy:
    base = search_policy_from_env()
    order = tuple(
        item.strip()
        for item in os.getenv("IDENTITY_SEARCH_PROVIDER_ORDER", "yandex,tavily,searxng").split(",")
        if item.strip()
    )
    debug = search_effectiveness_debug_enabled()
    return base.model_copy(
        update={
            "provider_order": order,
            "allowed_providers": frozenset(order),
            "strategy": SearchStrategy.FALLBACK_FIRST_NONEMPTY,
            "allow_paid_fallback": True if debug else _bool_env("IDENTITY_SEARCH_ALLOW_PAID_FALLBACK", base.allow_paid_fallback),
            "allow_paid_fanout": False,
            "retries": 0,
        }
    )


def _search_cache_from_env() -> SearchCache | None:
    path = os.getenv("SEARCH_CACHE_DB_PATH", "").strip()
    if not path:
        return None
    return SQLiteSearchCache(
        path,
        max_entries=_int_env(
            "SEARCH_CACHE_MAX_ENTRIES", 4096, minimum=128, maximum=100000
        ),
    )


@lru_cache(maxsize=1)
def get_search_gateway() -> TracedSearchGateway:
    debug = search_effectiveness_debug_enabled()
    quotas = {} if debug else {
        provider: quota
        for provider, quota in {
            "searxng": _quota_env("SEARCH_QUOTA_SEARXNG"),
            "yandex": _quota_env("SEARCH_QUOTA_YANDEX"),
            "tavily": _quota_env("SEARCH_QUOTA_TAVILY"),
        }.items()
        if quota is not None
    }

    yandex = _scheduled(
        YandexProvider(
            os.getenv("YANDEX_SEARCH_API_KEY"),
            first_nonempty_env("YANDEX_CLOUD_FOLDER_ID", "YANDEX_SEARCH_FOLDER_ID"),
            cost_amount=_decimal_env("YANDEX_SEARCH_COST_RUB"),
        ),
        concurrency_env="SEARCH_CONCURRENCY_YANDEX", concurrency_default=3,
        jitter_min_env="SEARCH_JITTER_YANDEX_MIN_SECONDS", jitter_min_default=0.0,
        jitter_max_env="SEARCH_JITTER_YANDEX_MAX_SECONDS", jitter_max_default=0.0,
    )
    searxng = _scheduled(
        SearxngProvider(
            os.getenv("SEARXNG_BASE_URL"),
            engines=_csv_env("SEARXNG_ENGINES", DEFAULT_SEARXNG_ENGINES),
            engine_fanout=_int_env(
                "SEARXNG_ENGINES_PER_REQUEST", 2, minimum=1, maximum=64
            ),
            engine_rate_limit_cooldown_seconds=_float_env(
                "SEARXNG_ENGINE_RATE_LIMIT_COOLDOWN_SECONDS",
                3600.0,
                minimum=0.0,
                maximum=604800.0,
            ),
            engine_block_cooldown_seconds=_float_env(
                "SEARXNG_ENGINE_BLOCK_COOLDOWN_SECONDS",
                86400.0,
                minimum=0.0,
                maximum=2592000.0,
            ),
            engine_error_cooldown_seconds=_float_env(
                "SEARXNG_ENGINE_ERROR_COOLDOWN_SECONDS",
                60.0,
                minimum=0.0,
                maximum=86400.0,
            ),
        ),
        concurrency_env="SEARCH_CONCURRENCY_SEARXNG", concurrency_default=1,
        jitter_min_env="SEARCH_JITTER_SEARXNG_MIN_SECONDS", jitter_min_default=0.2,
        jitter_max_env="SEARCH_JITTER_SEARXNG_MAX_SECONDS", jitter_max_default=0.8,
    )
    tavily = _scheduled(
        TavilyProvider(
            os.getenv("TAVILY_TOKEN") or os.getenv("TAVILY_API_KEY"),
            cost_amount=_decimal_env("TAVILY_SEARCH_COST_USD"),
            proxy_url=os.getenv("TAVILY_PROXY_URL"),
            contract_allowed=_bool_env("TAVILY_CONTRACT_ALLOWED", True),
        ),
        concurrency_env="SEARCH_CONCURRENCY_TAVILY", concurrency_default=3,
        jitter_min_env="SEARCH_JITTER_TAVILY_MIN_SECONDS", jitter_min_default=0.0,
        jitter_max_env="SEARCH_JITTER_TAVILY_MAX_SECONDS", jitter_max_default=0.0,
    )

    return TracedSearchGateway(
        [yandex, searxng, tavily],
        global_quotas=quotas,
        cache=_search_cache_from_env(),
    )


def reset_search_gateway() -> None:
    get_search_gateway.cache_clear()
