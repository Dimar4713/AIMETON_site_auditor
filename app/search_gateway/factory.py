from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation
from functools import lru_cache

from app.search_gateway.gateway import SearchGateway
from app.search_gateway.models import SearchPolicy
from app.search_gateway.providers import SearxngProvider, TavilyProvider, YandexProvider


def _decimal_env(name: str) -> Decimal:
    try:
        return Decimal(os.getenv(name, "0").strip() or "0")
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


def search_policy_from_env() -> SearchPolicy:
    order = tuple(
        item.strip()
        for item in os.getenv(
            "SEARCH_PROVIDER_ORDER",
            "yandex,searxng,tavily",
        ).split(",")
        if item.strip()
    )
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
        allow_paid_fallback=_bool_env("SEARCH_ALLOW_PAID_FALLBACK"),
        max_cost_by_currency=budgets,
        timeout_seconds=float(os.getenv("SEARCH_TIMEOUT_SECONDS", "15")),
        retries=int(os.getenv("SEARCH_RETRIES", "1")),
        cache_ttl_seconds=int(os.getenv("SEARCH_CACHE_TTL_SECONDS", "900")),
    )


@lru_cache(maxsize=1)
def get_search_gateway() -> SearchGateway:
    quotas = {
        provider: quota
        for provider, quota in {
            "searxng": _quota_env("SEARCH_QUOTA_SEARXNG"),
            "yandex": _quota_env("SEARCH_QUOTA_YANDEX"),
            "tavily": _quota_env("SEARCH_QUOTA_TAVILY"),
        }.items()
        if quota is not None
    }
    return SearchGateway(
        [
            YandexProvider(
                os.getenv("YANDEX_SEARCH_API_KEY"),
                os.getenv("YANDEX_SEARCH_FOLDER_ID"),
                cost_amount=_decimal_env("YANDEX_SEARCH_COST_RUB"),
            ),
            SearxngProvider(os.getenv("SEARXNG_BASE_URL")),
            TavilyProvider(
                os.getenv("TAVILY_API_KEY"),
                cost_amount=_decimal_env("TAVILY_SEARCH_COST_USD"),
            ),
        ],
        global_quotas=quotas,
    )


def reset_search_gateway() -> None:
    get_search_gateway.cache_clear()
