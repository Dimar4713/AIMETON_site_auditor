from __future__ import annotations

import base64
import html
import json
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
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


def collect_yandex(query: str, limit: int) -> list[dict]:
    api_key = (os.getenv("YANDEX_SEARCH_API_KEY") or "").strip()
    folder_id = (os.getenv("YANDEX_CLOUD_FOLDER_ID") or os.getenv("YANDEX_SEARCH_FOLDER_ID") or "").strip()
    if not api_key:
        raise RuntimeError("YANDEX_SEARCH_API_KEY missing")
    if not folder_id:
        raise RuntimeError("YANDEX_CLOUD_FOLDER_ID missing")
    if not folder_id.isascii():
        raise RuntimeError("YANDEX_CLOUD_FOLDER_ID must be ASCII")

    body = json.dumps(
        {
            "query": {
                "searchType": "SEARCH_TYPE_RU",
                "queryText": query,
                "familyMode": "FAMILY_MODE_MODERATE",
                "page": "0",
                "fixTypoMode": "FIX_TYPO_MODE_ON",
            },
            "groupSpec": {
                "groupMode": "GROUP_MODE_FLAT",
                "groupsOnPage": str(min(limit, 100)),
                "docsInGroup": "1",
            },
            "maxPassages": "3",
            "l10N": "LOCALIZATION_RU",
            "folderId": folder_id,
            "responseFormat": "FORMAT_XML",
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://searchapi.api.cloud.yandex.net/v2/web/search",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Api-Key {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "AIMETON-Search-Benchmark/1.0",
        },
    )
    payload = request_json(request)
    raw_data = payload.get("rawData")
    if not isinstance(raw_data, str):
        raise RuntimeError("Yandex returned no rawData")
    xml_text = base64.b64decode(raw_data, validate=True).decode("utf-8")
    root = ET.fromstring(xml_text)
    results: list[dict] = []
    for document in root.findall(".//doc"):
        url = document.findtext("url")
        if not url:
            continue
        passages = ["".join(passage.itertext()) for passage in document.findall(".//passage")]
        title_node = document.find("title")
        title = html.unescape("".join(title_node.itertext())) if title_node is not None else ""
        results.append(
            {
                "url": url,
                "title": title,
                "snippet": html.unescape(" ".join(passages)),
            }
        )
    return results[:limit]


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
    collectors = {
        "tavily": collect_tavily,
        "yandex": collect_yandex,
        "searxng": collect_searxng,
    }
    if provider not in collectors:
        raise SystemExit("SNAPSHOT_PROVIDER must be tavily, yandex or searxng")
    limit = int(os.getenv("SNAPSHOT_LIMIT") or "20")
    output = Path(os.getenv("SNAPSHOT_OUT") or f"/tmp/{provider}-snapshot.json")
    collector = collectors[provider]
    cost_amount = {"tavily": "0.008", "yandex": "0.01", "searxng": "0"}[provider]
    cost_currency = "RUB" if provider == "yandex" else "USD"

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
        "paid": provider in {"tavily", "yandex"},
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
