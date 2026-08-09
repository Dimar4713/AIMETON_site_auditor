from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from uuid import uuid4

from app.search_gateway import SearchPolicy, SearchRequest, SearchStrategy, get_search_gateway


async def main() -> None:
    gateway = get_search_gateway()
    query = "Стоматология Красноярск официальный сайт компания"
    failed: list[str] = []

    for provider in ("yandex", "tavily", "searxng"):
        mission = f"bench-provider-probe-{provider}-{uuid4()}"
        response = await gateway.search(
            SearchRequest(
                query=query,
                limit=10,
                mission_id=mission,
                correlation_id=mission,
            ),
            SearchPolicy(
                provider_order=(provider,),
                allowed_providers=frozenset({provider}),
                strategy=SearchStrategy.PRIMARY_ONLY,
                target_results=10,
                max_providers_per_query=1,
                allow_paid_fallback=True,
                allow_paid_fanout=True,
                max_cost_by_currency={"RUB": Decimal("999999"), "USD": Decimal("999999")},
                timeout_seconds=20.0,
                retries=0,
                cache_ttl_seconds=0,
            ),
        )
        attempts = [
            {
                "provider": attempt.provider,
                "state": str(attempt.state),
                "reason": str(attempt.reason) if attempt.reason else None,
                "latency_ms": attempt.latency_ms,
                "result_count": attempt.result_count,
                "cost_amount": str(attempt.cost_amount),
                "cost_currency": attempt.cost_currency,
            }
            for attempt in response.diagnostics.attempts
        ]
        hosts = []
        for item in response.results[:5]:
            host = str(item.url).split("/", 3)[2] if "://" in str(item.url) else str(item.url)
            hosts.append(host)
        print(
            "PROVIDER_PROBE "
            + json.dumps(
                {
                    "provider": provider,
                    "gateway_state": str(response.diagnostics.state),
                    "result_count": len(response.results),
                    "attempts": attempts,
                    "top_hosts": hosts,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            flush=True,
        )
        if not response.results or not attempts or attempts[0]["state"] != "succeeded":
            failed.append(provider)

    if failed:
        raise SystemExit("provider_preflight_failed:" + ",".join(failed))


if __name__ == "__main__":
    asyncio.run(main())
