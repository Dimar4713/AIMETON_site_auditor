from __future__ import annotations

import asyncio
from decimal import Decimal

from app.search_gateway import (
    SearchPolicy,
    SearchRequest,
    SearchStrategy,
    get_search_gateway,
    reset_search_gateway,
)


async def main() -> None:
    reset_search_gateway()
    gateway = get_search_gateway()
    policy = SearchPolicy(
        provider_order=("yandex",),
        allowed_providers=frozenset({"yandex"}),
        strategy=SearchStrategy.PRIMARY_ONLY,
        target_results=10,
        max_providers_per_query=1,
        allow_paid_fallback=True,
        allow_paid_fanout=True,
        max_cost_by_currency={"RUB": Decimal("1000"), "USD": Decimal("1000")},
        timeout_seconds=30.0,
        retries=0,
        cache_ttl_seconds=0,
    )
    response = await gateway.search(
        SearchRequest(
            query="Стоматология Красноярск официальный сайт компания",
            limit=10,
            mission_id="diag-yandex-search-gateway",
            correlation_id="diag-yandex-search-gateway-1",
        ),
        policy,
    )
    print(
        {
            "state": str(response.diagnostics.state),
            "selected_provider": response.diagnostics.selected_provider,
            "results": len(response.results),
            "attempts": [
                {
                    "provider": attempt.provider,
                    "state": str(attempt.state),
                    "count": attempt.result_count,
                    "reason": str(attempt.reason) if attempt.reason else None,
                }
                for attempt in response.diagnostics.attempts
            ],
        }
    )
    if response.diagnostics.selected_provider != "yandex" or not response.results:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
