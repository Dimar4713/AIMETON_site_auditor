from __future__ import annotations

import asyncio
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.search_gateway import (
    SearchDiagnostics,
    SearchRequest,
    get_search_gateway,
    search_policy_from_env,
)


DISCOVERY_TOPICS: tuple[tuple[str, int], ...] = (
    ("реквизиты ИНН ОГРН", 100),
    ("контакты адрес телефон", 90),
    ("лицензия документы", 85),
    ("услуги цены", 70),
    ("о компании", 60),
)


def _host(value: str) -> str:
    return (urlsplit(value).hostname or "").lower().removeprefix("www.")


def same_host_family(root_url: str, candidate_url: str) -> bool:
    root = _host(root_url)
    candidate = _host(candidate_url)
    return bool(root) and root == candidate


@dataclass(frozen=True)
class SameDomainDiscovery:
    urls: tuple[str, ...]
    diagnostics: SearchDiagnostics


async def discover_same_domain_urls(
    root_url: str,
    *,
    company_name: str | None,
    mission_id: str,
    correlation_id: str,
    max_urls: int = 8,
) -> SameDomainDiscovery:
    """Discover likely high-value first-party pages without treating snippets as evidence.

    Search is only a URL discovery mechanism. Only exact host-family URLs are
    returned; the Evidence Crawler remains responsible for robots policy,
    fetching and evidence extraction.
    """
    domain = _host(root_url)
    if not domain:
        return SameDomainDiscovery(
            urls=(),
            diagnostics=SearchDiagnostics.aggregate([]),
        )

    gateway = get_search_gateway()
    policy = search_policy_from_env()
    name = " ".join((company_name or "").split()).strip()

    async def search_topic(topic: str, priority: int):
        identity = f' "{name}"' if name else ""
        response = await gateway.search(
            SearchRequest(
                query=f"site:{domain}{identity} {topic}",
                limit=8,
                mission_id=mission_id,
                correlation_id=f"{correlation_id}-same-domain-{priority}",
            ),
            policy,
        )
        return priority, response

    batches = await asyncio.gather(
        *(search_topic(topic, priority) for topic, priority in DISCOVERY_TOPICS)
    )
    diagnostics = SearchDiagnostics.aggregate(
        [response.diagnostics for _, response in batches]
    )

    ranked: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    for priority, response in batches:
        for position, item in enumerate(response.results):
            value = str(item.url)
            if not same_host_family(root_url, value) or value in seen:
                continue
            seen.add(value)
            ranked.append((-priority, position, value))

    ranked.sort()
    return SameDomainDiscovery(
        urls=tuple(value for _, _, value in ranked[:max_urls]),
        diagnostics=diagnostics,
    )
