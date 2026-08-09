from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path


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


def request_json(request: urllib.request.Request, timeout: float = 25.0) -> dict:
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def collect_tavily(query: str, limit: int) -> list[dict]:
    token = (os.getenv("TAVILY_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("TAVILY_TOKEN missing")
    body = json.dumps(
        {
            "query": query,
            "search_depth": "basic",
            "max_results": limit,
            "include_answer": False,
            "include_raw_content": False,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.tavily.com/search",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "AIMETON-Search-Benchmark/1.0",
        },
    )
    payload = request_json(request)
    return [
        {
            "url": str(item.get("url") or ""),
            "title": str(item.get("title") or ""),
            "snippet": str(item.get("content") or item.get("snippet") or ""),
        }
        for item in payload.get("results", [])
        if item.get("url")
    ]


def collect_searxng(query: str, limit: int) -> list[dict]:
    base = (os.getenv("SEARXNG_BASE_URL") or "http://searxng:8080").rstrip("/")
    params = urllib.parse.urlencode(
        {
            "q": query,
            "format": "json",
            "language": "ru-RU",
            "safesearch": "1",
        }
    )
    request = urllib.request.Request(
        f"{base}/search?{params}",
        method="GET",
        headers={"Accept": "application/json", "User-Agent": "AIMETON-Search-Benchmark/1.0"},
    )
    payload = request_json(request)
    return [
        {
            "url": str(item.get("url") or ""),
            "title": str(item.get("title") or ""),
            "snippet": str(item.get("content") or item.get("snippet") or ""),
        }
        for item in payload.get("results", [])[:limit]
        if item.get("url")
    ]


def main() -> None:
    provider = (os.getenv("SNAPSHOT_PROVIDER") or "").strip().lower()
    if provider not in {"tavily", "searxng"}:
        raise SystemExit("SNAPSHOT_PROVIDER must be tavily or searxng")
    limit = int(os.getenv("SNAPSHOT_LIMIT") or "20")
    output = Path(os.getenv("SNAPSHOT_OUT") or f"/tmp/{provider}-snapshot.json")
    collector = collect_tavily if provider == "tavily" else collect_searxng
    cost_amount = "0.008" if provider == "tavily" else "0"
    cost_currency = "USD"

    queries: dict[str, dict] = {}
    for query in QUERY_VARIANTS:
        started = time.perf_counter()
        results = collector(query, limit)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        queries[query] = {"latency_ms": elapsed_ms, "results": results}
        print(
            "SNAPSHOT_QUERY "
            + json.dumps(
                {"provider": provider, "query": query, "results": len(results), "latency_ms": elapsed_ms},
                ensure_ascii=False,
                sort_keys=True,
            ),
            flush=True,
        )

    payload = {
        "provider": provider,
        "paid": provider == "tavily",
        "cost_amount_per_call": cost_amount,
        "cost_currency": cost_currency,
        "limit": limit,
        "queries": queries,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        "SNAPSHOT_DONE "
        + json.dumps(
            {
                "provider": provider,
                "queries": len(queries),
                "total_results": sum(len(row["results"]) for row in queries.values()),
                "modeled_cost": str(float(cost_amount) * len(queries)),
                "currency": cost_currency,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
