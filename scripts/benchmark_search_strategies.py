from __future__ import annotations

import asyncio
import json
import os
import time
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from app.search_gateway.gateway import SearchGateway, canonical_url
from app.search_gateway.models import AttemptState, SearchPolicy, SearchRequest, SearchStrategy
from app.search_gateway.providers import SearxngProvider, TavilyProvider, YandexProvider
from app.search_gateway.scheduler import ScheduledProvider


QUERY_VARIANTS = [
    "Стоматология Красноярск официальный сайт компания",
    "Стоматологическая клиника Красноярск официальный сайт компания",
    "Стоматологический центр Красноярск официальный сайт компания",
    "Стоматология Красноярск клиника адрес телефон",
    "Стоматология Красноярск имплантация клиника",
    "Стоматология Красноярск ортодонтия клиника",
    "Стоматология Красноярск детская клиника",
    "Стоматология Красноярск лечение зубов официальный сайт",
]

SUPPORTING_HOST_MARKERS = (
    "2gis.", "yandex.", "google.", "zoon.", "prodoctorov.", "startsmile.", "topdent.",
    "32top.", "flamp.", "yell.", "kp.ru", "ngs.ru", "vk.com", "ok.ru", "t.me",
    "youtube.", "rutube.", "hh.ru", "superjob.", "rusprofile.", "checko.", "list-org.",
    "companies.rbc.", "audit-it.", "spravker.", "orgpage.", "mestam.info", "blizko.",
)
SUPPORTING_TEXT_MARKERS = (
    "рейтинг стоматолог", "каталог стоматолог", "список стоматолог", "отзывы о стоматолог",
    "лучшие стоматолог", "врачи стоматолог", "вакансии стоматолог", "стоматологии на карте",
)
DENTISTRY_MARKERS = (
    "стоматолог", "стоматология", "стоматологичес", "dent", "dental", "зуб", "ортодонт",
    "имплант", "эндодонт", "пародонт",
)
REGION_MARKERS = ("краснояр", "krasnoyarsk", "krsk")


def dec_env(name: str, default: str = "0") -> Decimal:
    try:
        return Decimal((os.getenv(name) or default).strip() or default)
    except Exception:
        return Decimal(default)


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def classify(url: str, title: str, snippet: str) -> str:
    host = host_of(url)
    text = f"{title} {snippet} {url}".casefold().replace("ё", "е")
    if any(marker in host for marker in SUPPORTING_HOST_MARKERS) or any(marker in text for marker in SUPPORTING_TEXT_MARKERS):
        return "supporting"
    if any(marker in text for marker in DENTISTRY_MARKERS):
        return "direct_company"
    return "other"


def region_match(url: str, title: str, snippet: str) -> bool:
    text = f"{title} {snippet} {url}".casefold().replace("ё", "е")
    return any(marker in text for marker in REGION_MARKERS)


def make_gateway() -> SearchGateway:
    searx_url = (os.getenv("SEARXNG_BASE_URL") or "").strip()
    tavily_key = (os.getenv("TAVILY_TOKEN") or os.getenv("TAVILY_API_KEY") or "").strip()
    yandex_key = (os.getenv("YANDEX_SEARCH_API_KEY") or "").strip()
    yandex_folder = (os.getenv("YANDEX_CLOUD_FOLDER_ID") or os.getenv("YANDEX_SEARCH_FOLDER_ID") or "").strip()

    providers = [
        ScheduledProvider(
            YandexProvider(yandex_key, yandex_folder, cost_amount=dec_env("YANDEX_SEARCH_COST_RUB", "0.01")),
            max_concurrency=3,
        ),
        ScheduledProvider(
            TavilyProvider(tavily_key, cost_amount=dec_env("TAVILY_SEARCH_COST_USD", "0.008")),
            max_concurrency=3,
        ),
        ScheduledProvider(
            SearxngProvider(searx_url),
            max_concurrency=2,
            jitter_min_seconds=0.2,
            jitter_max_seconds=0.8,
        ),
    ]
    states = {provider.name: provider.configured for provider in providers}
    if not all(states.values()):
        raise RuntimeError(f"benchmark providers not configured: {states}")
    return SearchGateway(providers, global_quotas={})


def policy_for(strategy: SearchStrategy) -> SearchPolicy:
    return SearchPolicy(
        provider_order=("yandex", "tavily", "searxng"),
        allowed_providers=frozenset({"yandex", "tavily", "searxng"}),
        strategy=strategy,
        target_results=30,
        max_providers_per_query=3,
        allow_paid_fallback=True,
        allow_paid_fanout=True,
        max_cost_by_currency={"RUB": Decimal("999999"), "USD": Decimal("999999")},
        timeout_seconds=20.0,
        retries=1,
        cache_ttl_seconds=0,
    )


async def run_strategy(strategy: SearchStrategy) -> dict:
    gateway = make_gateway()
    policy = policy_for(strategy)
    mission_id = f"bench-krasnoyarsk-dentistry-{strategy}-{uuid4()}"
    started = time.perf_counter()
    records: dict[str, dict] = {}
    attempts = []
    query_counts = []

    for index, query in enumerate(QUERY_VARIANTS, start=1):
        response = await gateway.search(
            SearchRequest(
                query=query,
                limit=20,
                language="ru-RU",
                mission_id=mission_id,
                correlation_id=f"bench-{strategy}-{index}",
            ),
            policy,
        )
        query_counts.append(len(response.results))
        attempts.extend(response.diagnostics.attempts)
        for item in response.results:
            url = canonical_url(str(item.url))
            host = host_of(url)
            if not host:
                continue
            row = records.setdefault(
                url,
                {
                    "url": url,
                    "host": host,
                    "title": item.title,
                    "snippet": item.snippet,
                    "providers": set(),
                    "queries": set(),
                    "corroborated_by": set(),
                },
            )
            row["providers"].add(item.provider)
            row["queries"].add(query)
            row["corroborated_by"].update(item.corroborated_by or [item.provider])
            if not row["title"] and item.title:
                row["title"] = item.title
            if not row["snippet"] and item.snippet:
                row["snippet"] = item.snippet

    elapsed = time.perf_counter() - started
    domains: dict[str, dict] = {}
    for row in records.values():
        cls = classify(row["url"], row["title"], row["snippet"])
        row["class"] = cls
        row["region_match"] = region_match(row["url"], row["title"], row["snippet"])
        domain = domains.setdefault(
            row["host"],
            {
                "host": row["host"],
                "classes": Counter(),
                "providers": set(),
                "queries": set(),
                "titles": [],
                "region_match": False,
                "corroborated_by": set(),
            },
        )
        domain["classes"][cls] += 1
        domain["providers"].update(row["providers"])
        domain["queries"].update(row["queries"])
        domain["corroborated_by"].update(row["corroborated_by"])
        domain["region_match"] = domain["region_match"] or row["region_match"]
        if row["title"] and row["title"] not in domain["titles"] and len(domain["titles"]) < 3:
            domain["titles"].append(row["title"][:180])

    direct_domains = {
        host for host, row in domains.items()
        if row["classes"]["direct_company"] > 0 and row["classes"]["supporting"] == 0
    }
    supporting_domains = {
        host for host, row in domains.items()
        if row["classes"]["supporting"] > 0
    }
    regional_direct_domains = {host for host in direct_domains if domains[host]["region_match"]}
    corroborated_domains = {
        host for host in domains
        if len(domains[host]["corroborated_by"] | domains[host]["providers"]) >= 2
    }

    calls = Counter()
    states = Counter()
    costs: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    latency_by_provider: dict[str, int] = defaultdict(int)
    for attempt in attempts:
        states[f"{attempt.provider}:{attempt.state}"] += 1
        if attempt.state in {AttemptState.SUCCEEDED, AttemptState.EMPTY, AttemptState.FAILED}:
            calls[attempt.provider] += 1
            latency_by_provider[attempt.provider] += attempt.latency_ms
            costs[attempt.cost_currency] += attempt.cost_amount

    top_direct = sorted(
        (
            {
                "host": host,
                "query_hits": len(domains[host]["queries"]),
                "providers": sorted(domains[host]["providers"]),
                "corroborated_by": sorted(domains[host]["corroborated_by"]),
                "region_match": bool(domains[host]["region_match"]),
                "title": domains[host]["titles"][0] if domains[host]["titles"] else host,
            }
            for host in direct_domains
        ),
        key=lambda x: (-x["query_hits"], -len(set(x["providers"]) | set(x["corroborated_by"])), x["host"]),
    )[:25]

    return {
        "strategy": str(strategy),
        "elapsed_seconds": round(elapsed, 3),
        "query_count": len(QUERY_VARIANTS),
        "per_query_result_counts": query_counts,
        "unique_urls": len(records),
        "unique_domains": len(domains),
        "direct_domains": sorted(direct_domains),
        "regional_direct_domains": sorted(regional_direct_domains),
        "supporting_domains": sorted(supporting_domains),
        "corroborated_domains": sorted(corroborated_domains),
        "provider_calls": dict(calls),
        "attempt_states": dict(states),
        "provider_latency_ms": dict(latency_by_provider),
        "costs": {currency: str(amount) for currency, amount in sorted(costs.items())},
        "top_direct": top_direct,
    }


def finalize(rows: list[dict]) -> dict:
    reference_direct: set[str] = set()
    reference_regional: set[str] = set()
    for row in rows:
        reference_direct.update(row["direct_domains"])
        reference_regional.update(row["regional_direct_domains"])

    max_elapsed = max((row["elapsed_seconds"] for row in rows), default=1.0) or 1.0
    max_paid_calls = max(
        (row["provider_calls"].get("yandex", 0) + row["provider_calls"].get("tavily", 0) for row in rows),
        default=1,
    ) or 1

    for row in rows:
        direct = set(row["direct_domains"])
        regional = set(row["regional_direct_domains"])
        precision = len(direct) / max(1, row["unique_domains"])
        recall = len(direct) / max(1, len(reference_direct))
        regional_recall = len(regional) / max(1, len(reference_regional))
        corroboration = len(set(row["corroborated_domains"]) & direct) / max(1, len(direct))
        paid_calls = row["provider_calls"].get("yandex", 0) + row["provider_calls"].get("tavily", 0)
        time_eff = 1.0 - min(1.0, row["elapsed_seconds"] / max_elapsed)
        cost_eff = 1.0 - min(1.0, paid_calls / max_paid_calls)
        efficiency = (time_eff + cost_eff) / 2
        score = 100 * (0.50 * recall + 0.35 * precision + 0.10 * corroboration + 0.05 * efficiency)
        row["metrics"] = {
            "precision": round(precision, 4),
            "benchmark_recall": round(recall, 4),
            "regional_recall": round(regional_recall, 4),
            "corroboration": round(corroboration, 4),
            "efficiency": round(efficiency, 4),
            "score": round(score, 2),
            "paid_calls": paid_calls,
        }

    ranked = sorted(rows, key=lambda row: (-row["metrics"]["score"], row["elapsed_seconds"], row["strategy"]))
    for rank, row in enumerate(ranked, start=1):
        row["rank"] = rank

    return {
        "benchmark": {
            "logical_query": "Красноярск ; Стоматология",
            "query_variants": QUERY_VARIANTS,
            "provider_order": ["yandex", "tavily", "searxng"],
            "request_limit": 20,
            "target_results": 30,
            "max_providers_per_query": 3,
            "paid_fallback": True,
            "paid_fanout": True,
            "budget_caps": {"RUB": "999999", "USD": "999999"},
            "reference_direct_domain_count": len(reference_direct),
            "reference_regional_direct_domain_count": len(reference_regional),
            "reference_direct_domains": sorted(reference_direct),
        },
        "strategies": ranked,
    }


def markdown(result: dict) -> str:
    lines = [
        "# Krasnoyarsk dentistry Search Gateway benchmark",
        "",
        "Logical query: `Красноярск ; Стоматология`",
        "",
        f"Reference union: {result['benchmark']['reference_direct_domain_count']} probable direct-company domains; regional-evidence subset: {result['benchmark']['reference_regional_direct_domain_count']}.",
        "",
        "| Rank | Strategy | Score | Direct domains | Precision | Recall | Regional recall | Corroboration | Seconds | Calls Y/T/S | Cost RUB | Cost USD |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|",
    ]
    for row in result["strategies"]:
        m = row["metrics"]
        calls = row["provider_calls"]
        lines.append(
            f"| {row['rank']} | `{row['strategy']}` | {m['score']:.2f} | {len(row['direct_domains'])} | {m['precision']:.1%} | {m['benchmark_recall']:.1%} | {m['regional_recall']:.1%} | {m['corroboration']:.1%} | {row['elapsed_seconds']:.2f} | {calls.get('yandex',0)}/{calls.get('tavily',0)}/{calls.get('searxng',0)} | {row['costs'].get('RUB','0')} | {row['costs'].get('USD','0')} |"
        )
    lines += ["", "## Top probable direct companies by strategy", ""]
    for row in result["strategies"]:
        lines.append(f"### {row['rank']}. `{row['strategy']}`")
        for item in row["top_direct"][:15]:
            prov = ",".join(sorted(set(item["providers"]) | set(item["corroborated_by"]))) or "-"
            region = "region+" if item["region_match"] else "region?"
            lines.append(f"- `{item['host']}` — {item['title']} — q={item['query_hits']} — {prov} — {region}")
        lines.append("")
    return "\n".join(lines)


async def main() -> None:
    rows = []
    for strategy in SearchStrategy:
        print(f"BENCH_START strategy={strategy}", flush=True)
        row = await run_strategy(strategy)
        rows.append(row)
        print(
            "BENCH_DONE "
            + json.dumps(
                {
                    "strategy": row["strategy"],
                    "seconds": row["elapsed_seconds"],
                    "unique_domains": row["unique_domains"],
                    "direct_domains": len(row["direct_domains"]),
                    "calls": row["provider_calls"],
                    "costs": row["costs"],
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            flush=True,
        )

    result = finalize(rows)
    out = Path(os.getenv("BENCHMARK_OUT", "/tmp/search-strategy-benchmark"))
    out.mkdir(parents=True, exist_ok=True)
    (out / "benchmark.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md = markdown(result)
    (out / "summary.md").write_text(md, encoding="utf-8")
    print("BENCHMARK_SUMMARY_BEGIN", flush=True)
    print(md, flush=True)
    print("BENCHMARK_SUMMARY_END", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
