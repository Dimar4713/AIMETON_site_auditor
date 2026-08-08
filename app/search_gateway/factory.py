from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation
from functools import lru_cache

from app.search_gateway.factory_helpers import first_nonempty_env
from app.search_gateway.models import SearchPolicy
from app.search_gateway.providers import SearxngProvider, TavilyProvider, YandexProvider
from app.search_gateway.traced_gateway import TracedSearchGateway


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


def search_effectiveness_debug_enabled() -> bool:
    """Return whether search quality is intentionally prioritized over internal cost caps.

    This temporary mode is governed by #427. It removes AIMETON-internal budget
    and quota throttles while preserving provider hard limits, timeouts, circuit
    breakers and all crawler/security controls.
    """
    return _bool_env("SEARCH_EFFECTIVENESS_DEBUG")


def search_policy_from_env() -> SearchPolicy:
    order = tuple(
        item.strip()
        for item in os.getenv(
            "SEARCH_PROVIDER_ORDER",
            "yandex,searxng,tavily",
        ).split(",")
        if item.strip()
    )
    debug = search_effectiveness_debug_enabled()
    if debug:
        budgets = {
            "RUB": DEBUG_BUDGET_CEILING,
            "USD": DEBUG_BUDGET_CEILING,
        }
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
        allow_paid_fallback=True if debug else _bool_env("SEARCH_ALLOW_PAID_FALLBACK"),
        max_cost_by_currency=budgets,
        timeout_seconds=float(os.getenv("SEARCH_TIMEOUT_SECONDS", "15")),
        retries=int(os.getenv("SEARCH_RETRIES", "1")),
        cache_ttl_seconds=int(os.getenv("SEARCH_CACHE_TTL_SECONDS", "900")),
    )


def identity_search_policy_from_env() -> SearchPolicy:
    base = search_policy_from_env()
    order = tuple(
        item.strip()
        for item in os.getenv(
            "IDENTITY_SEARCH_PROVIDER_ORDER",
            "yandex,tavily,searxng",
        ).split(",")
        if item.strip()
    )
    debug = search_effectiveness_debug_enabled()
    return base.model_copy(
        update={
            "provider_order": order,
            "allowed_providers": frozenset(order),
            "allow_paid_fallback": True if debug else _bool_env(
                "IDENTITY_SEARCH_ALLOW_PAID_FALLBACK",
                base.allow_paid_fallback,
            ),
            "retries": 0,
        }
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
    return TracedSearchGateway(
        [
            YandexProvider(
                os.getenv("YANDEX_SEARCH_API_KEY"),
                first_nonempty_env(
                    "YANDEX_CLOUD_FOLDER_ID",
                    "YANDEX_SEARCH_FOLDER_ID",
                ),
                cost_amount=_decimal_env("YANDEX_SEARCH_COST_RUB"),
            ),
            SearxngProvider(
                os.getenv("SEARXNG_BASE_URL"),
                engines=_csv_env("SEARXNG_ENGINES", DEFAULT_SEARXNG_ENGINES),
            ),
            TavilyProvider(
                os.getenv("TAVILY_TOKEN") or os.getenv("TAVILY_API_KEY"),
                cost_amount=_decimal_env("TAVILY_SEARCH_COST_USD"),
            ),
        ],
        global_quotas=quotas,
    )


def reset_search_gateway() -> None:
    get_search_gateway.cache_clear()
