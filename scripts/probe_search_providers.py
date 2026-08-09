from __future__ import annotations

import asyncio
import json
from uuid import uuid4

from app.search_gateway import SearchRequest, get_search_gateway
from app.search_gateway.providers import ProviderError


async def main() -> None:
    gateway = get_search_gateway()
    query = "Стоматология Красноярск официальный сайт компания"
    failed: list[str] = []

    for provider_name in ("yandex", "tavily", "searxng"):
        provider = gateway._providers[provider_name]
        mission = f"bench-provider-probe-{provider_name}-{uuid4()}"
        request = SearchRequest(
            query=query,
            limit=10,
            mission_id=mission,
            correlation_id=mission,
        )
        try:
            results = await provider.search(request, timeout_seconds=20.0)
        except ProviderError as exc:
            print(
                "PROVIDER_DIRECT_FAILURE "
                + json.dumps(
                    {
                        "provider": provider_name,
                        "exception": type(exc).__name__,
                        "reason": str(exc),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                flush=True,
            )
            failed.append(provider_name)
            continue
        except Exception as exc:
            print(
                "PROVIDER_DIRECT_FAILURE "
                + json.dumps(
                    {
                        "provider": provider_name,
                        "exception": type(exc).__name__,
                        "reason": str(exc)[:300],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                flush=True,
            )
            failed.append(provider_name)
            continue

        hosts = []
        for item in results[:5]:
            url = str(item.url)
            host = url.split("/", 3)[2] if "://" in url else url
            hosts.append(host)
        print(
            "PROVIDER_DIRECT_SUCCESS "
            + json.dumps(
                {
                    "provider": provider_name,
                    "result_count": len(results),
                    "top_hosts": hosts,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            flush=True,
        )
        if not results:
            failed.append(provider_name)

    if failed:
        raise SystemExit("provider_preflight_failed:" + ",".join(failed))


if __name__ == "__main__":
    asyncio.run(main())
