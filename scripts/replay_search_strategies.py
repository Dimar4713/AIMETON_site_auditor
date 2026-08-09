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
from app.search_gateway.models import AttemptState, SearchItem, SearchPolicy, SearchRequest, SearchStrategy
from app.search_gateway.providers import SearchProvider
from app.search_gateway.scheduler import ScheduledProvider


SUPPORTING_HOST_MARKERS = (
    "2gis.", "yandex.", "google.", "zoon.", "prodoctorov.", "startsmile.", "topdent.",
    "32top.", "flamp.", "yell.", "kp.ru", "ngs.ru", "vk.com", "ok.ru", "t.me",
    "youtube.", "rutube.", "hh.ru", "superjob.", "rusprofile.", "checko.", "list-org.",
    "companies.rbc.", "audit-it.", "spravker.", "orgpage.", "mestam.info", "blizko.",
    "infodoctor.", "alldantist.", "dentistfind.", "doctu.", "kleos.", "napopravku.", "jsprav.",
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


class ReplayProvider(SearchProvider):
    def __init__(self, snapshot: dict, *, latency_scale: float = 1.0) -> None:
        self.snapshot = snapshot
        self.name = snapshot["provider"]
        self.paid = bool(snapshot.get("paid"))
        self.cost_amount = Decimal(str(snapshot.get("cost_amount_per_call") or "0"))
        self.cost_currency = str(snapshot.get("cost_currency") or "USD")
        self.latency_scale = max(0.0, latency_scale)

    @property
    def configured(self) -> bool:
        return True

    async def search(self, request: SearchRequest, *, timeout_seconds: float) -> list[SearchItem]:
        row = self.snapshot["queries"].get(request.query)
        if row is None:
            return []
        latency = max(0, int(row.get("latency_ms") or 0)) / 1000.0 * self.latency_scale
        if latency:
            await asyncio.sleep(min(latency, timeout_seconds))
        return [
            SearchItem(
                url=item["url"],
                title=item.get("title") or "",
                snippet=item.get("snippet") or "",
                provider=self.name,
                corroborated_by=[self.name],
            )
            for item in row.get("results", [])[: request.limit]
            if item.get("url")
        ]


def load_snapshots() -> list[dict]:
    paths = [Path(p) for p in (os.getenv("SNAPSHOT_FILES") or "").split(":") if p]
    if not paths:
        raise RuntimeError("SNAPSHOT_FILES missing")
    snapshots = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    names = [item["provider"] for item in snapshots]
    if len(names) != len(set(names)):
        raise RuntimeError(f"duplicate snapshot providers: {names}")
    return snapshots


def make_gateway(snapshots: list[dict]) -> SearchGateway:
    scale = float(os.getenv("REPLAY_LATENCY_SCALE") or "1")
    providers = [
        ScheduledProvider(ReplayProvider(snapshot, latency_scale=scale), max_concurrency=3)
        for snapshot in snapshots
    ]
    return SearchGateway(providers, global_quotas={})


def policy_for(strategy: SearchStrategy, order: tuple[str, ...]) -> SearchPolicy:
    return SearchPolicy(
        provider_order=order,
        allowed_providers=frozenset(order),
        strategy=strategy,
        target_results=30,
        max_providers_per_query=len(order),
        allow_paid_fallback=True,
        allow_paid_fanout=True,
        max_cost_by_currency={"RUB": Decimal("999999"), "USD": Decimal("999999")},
        timeout_seconds=30.0,
        retries=0,
        cache_ttl_seconds=0,
    )


async def run_strategy(strategy: SearchStrategy, snapshots: list[dict], queries: list[str], order: tuple[str, ...]) -> dict:
    gateway = make_gateway(snapshots)
    policy = policy_for(strategy, order)
    mission_id = f"replay-krasnoyarsk-dentistry-{strategy}-{uuid4()}"
    started = time.perf_counter()
    records: dict[str, dict] = {}
    attempts = []

    for index, query in enumerate(queries, start=1):
        response = await gateway.search(
            SearchRequest(
                query=query,
                limit=20,
                language="ru-RU",
                mission_id=mission_id,
                correlation_id=f"replay-{strategy}-{index}",
            ),
            policy,
        )
        attempts.extend(response.diagnostics.attempts)
        for item in response.results:
            url = canonical_url(str(item.url))
            host = host_of(url)
            if not host:
                continue
            row = records.setdefault(
                url,
                {"url": url, "host": host, "title": item.title, "snippet": item.snippet, "providers": set(), "queries": set(), "corroborated_by": set()},
            )
            row["providers"].add(item.provider)
            row["queries"].add(query)
            row["corroborated_by"].update(item.corroborated_by or [item.provider])

    elapsed = time.perf_counter() - started
    domains: dict[str, dict] = {}
    for row in records.values():
        cls = classify(row["url"], row["title"], row["snippet"])
        domain = domains.setdefault(
            row["host"],
            {"classes": Counter(), "providers": set(), "queries": set(), "titles": [], "region_match": False, "corroborated_by": set()},
        )
        domain["classes"][cls] += 1
        domain["providers"].update(row["providers"])
        domain["queries"].update(row["queries"])
        domain["corroborated_by"].update(row["corroborated_by"])
        domain["region_match"] = domain["region_match"] or region_match(row["url"], row["title"], row["snippet"])
        if row["title"] and row["title"] not in domain["titles"] and len(domain["titles"]) < 3:
            domain["titles"].append(row["title"][:180])

    direct = {host for host, row in domains.items() if row["classes"]["direct_company"] > 0 and row["classes"]["supporting"] == 0}
    regional = {host for host in direct if domains[host]["region_match"]}
    supporting = {host for host, row in domains.items() if row["classes"]["supporting"] > 0}
    corroborated = {host for host in direct if len(domains[host]["corroborated_by"] | domains[host]["providers"]) >= 2}

    calls = Counter()
    costs: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for attempt in attempts:
        if attempt.state in {AttemptState.SUCCEEDED, AttemptState.EMPTY, AttemptState.FAILED}:
            calls[attempt.provider] += 1
            costs[attempt.cost_currency] += attempt.cost_amount

    top_direct = sorted(
        ({"host": host, "query_hits": len(domains[host]["queries"]), "providers": sorted(domains[host]["providers"]), "title": domains[host]["titles"][0] if domains[host]["titles"] else host} for host in direct),
        key=lambda item: (-item["query_hits"], -len(item["providers"]), item["host"]),
    )[:20]

    return {
        "strategy": str(strategy),
        "elapsed_seconds": round(elapsed, 3),
        "unique_domains": len(domains),
        "direct_domains": sorted(direct),
        "regional_direct_domains": sorted(regional),
        "supporting_domains": sorted(supporting),
        "corroborated_domains": sorted(corroborated),
        "provider_calls": dict(calls),
        "costs": {currency: str(amount) for currency, amount in sorted(costs.items())},
        "top_direct": top_direct,
    }


def finalize(rows: list[dict], providers: list[str], queries: list[str]) -> dict:
    reference_direct = set().union(*(set(row["direct_domains"]) for row in rows))
    reference_regional = set().union(*(set(row["regional_direct_domains"]) for row in rows))
    max_elapsed = max((row["elapsed_seconds"] for row in rows), default=1.0) or 1.0
    max_paid_calls = max((sum(row["provider_calls"].get(name, 0) for name in providers if name != "searxng") for row in rows), default=1) or 1

    for row in rows:
        direct = set(row["direct_domains"])
        regional = set(row["regional_direct_domains"])
        precision = len(direct) / max(1, row["unique_domains"])
        recall = len(direct) / max(1, len(reference_direct))
        regional_recall = len(regional) / max(1, len(reference_regional))
        corroboration = len(set(row["corroborated_domains"])) / max(1, len(direct))
        paid_calls = sum(row["provider_calls"].get(name, 0) for name in providers if name != "searxng")
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
        }

    ranked = sorted(rows, key=lambda row: (-row["metrics"]["score"], row["elapsed_seconds"], row["strategy"]))
    for rank, row in enumerate(ranked, start=1):
        row["rank"] = rank
    return {
        "benchmark": {
            "logical_query": "Красноярск ; Стоматология",
            "mode": "live-snapshot-replay",
            "providers": providers,
            "query_variants": queries,
            "reference_direct_domain_count": len(reference_direct),
            "reference_regional_direct_domain_count": len(reference_regional),
            "score_formula": "50% recall + 35% precision + 10% corroboration + 5% time/cost efficiency",
        },
        "strategies": ranked,
    }


def markdown(result: dict) -> str:
    providers = result["benchmark"]["providers"]
    lines = [
        "# Krasnoyarsk dentistry Search Gateway snapshot/replay benchmark",
        "",
        f"Providers: {', '.join(providers)}",
        f"Reference union: {result['benchmark']['reference_direct_domain_count']} probable direct-company domains; regional subset: {result['benchmark']['reference_regional_direct_domain_count']}.",
        "",
        "| Rank | Strategy | Score | Direct | Precision | Recall | Regional recall | Corroboration | Simulated seconds | Calls | Cost RUB | Cost USD |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|",
    ]
    for row in result["strategies"]:
        m = row["metrics"]
        calls = "/".join(f"{name}:{row['provider_calls'].get(name, 0)}" for name in providers)
        lines.append(
            f"| {row['rank']} | `{row['strategy']}` | {m['score']:.2f} | {len(row['direct_domains'])} | {m['precision']:.1%} | {m['benchmark_recall']:.1%} | {m['regional_recall']:.1%} | {m['corroboration']:.1%} | {row['elapsed_seconds']:.2f} | {calls} | {row['costs'].get('RUB','0')} | {row['costs'].get('USD','0')} |"
        )
    lines.extend(["", "## Top probable direct-company domains", ""])
    for row in result["strategies"]:
        lines.append(f"### {row['rank']}. `{row['strategy']}`")
        for item in row["top_direct"][:12]:
            lines.append(f"- `{item['host']}` — {item['title']} — q={item['query_hits']} — {','.join(item['providers'])}")
        lines.append("")
    return "\n".join(lines)


async def main() -> None:
    snapshots = load_snapshots()
    providers = [snapshot["provider"] for snapshot in snapshots]
    preferred = [name for name in ("yandex", "tavily", "searxng") if name in providers]
    order = tuple(preferred)
    queries = list(snapshots[0]["queries"].keys())
    for snapshot in snapshots[1:]:
        if list(snapshot["queries"].keys()) != queries:
            raise RuntimeError("snapshot query sets/order differ")

    rows = []
    for strategy in SearchStrategy:
        print(f"REPLAY_START strategy={strategy}", flush=True)
        row = await run_strategy(strategy, snapshots, queries, order)
        rows.append(row)
        print("REPLAY_DONE " + json.dumps({"strategy": row["strategy"], "direct": len(row["direct_domains"]), "calls": row["provider_calls"], "costs": row["costs"]}, ensure_ascii=False, sort_keys=True), flush=True)

    result = finalize(rows, list(order), queries)
    out = Path(os.getenv("REPLAY_OUT") or "/tmp/search-strategy-replay")
    out.mkdir(parents=True, exist_ok=True)
    (out / "benchmark.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = markdown(result)
    (out / "summary.md").write_text(summary, encoding="utf-8")
    print(summary, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
