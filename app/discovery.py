from __future__ import annotations

import asyncio
import os
from urllib.parse import urlparse

import httpx

from app.heuristics import heuristic_analysis
from app.models import HuntCandidate, HuntRequest, HuntResult
from app.scraper import FetchError, fetch_site


DEFAULT_INDUSTRIES = [
    "отопление и вентиляция",
    "строительные материалы",
    "промышленное оборудование",
    "автозапчасти и автосервис",
    "мебель и кухни",
    "окна двери фасады",
    "стоматология и медицинские центры",
    "недвижимость и строительство",
    "образовательные центры",
    "туризм и базы отдыха",
]

EXCLUDED_HOSTS = {
    "vk.com",
    "t.me",
    "youtube.com",
    "rutube.ru",
    "instagram.com",
    "facebook.com",
    "2gis.ru",
    "yandex.ru",
    "google.com",
    "avito.ru",
    "hh.ru",
}


def _domain(url: str) -> str:
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    return host


def _build_queries(req: HuntRequest) -> list[str]:
    industries = req.industries or DEFAULT_INDUSTRIES
    queries: list[str] = []
    for industry in industries:
        queries.append(f'{industry} {req.region} официальный сайт компания')
        if req.search_zone:
            queries.append(f'{industry} {req.search_zone} {req.region} официальный сайт')
    for focus in req.focus:
        queries.append(f'{focus} {req.region} компания официальный сайт')
    return queries[: req.max_queries]


async def _search_searxng(query: str, limit: int) -> list[dict]:
    base_url = os.getenv("SEARXNG_BASE_URL")
    if not base_url:
        raise RuntimeError("SEARXNG_BASE_URL не задан")
    params = {"q": query, "format": "json", "language": "ru-RU"}
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.get(f"{base_url.rstrip('/')}/search", params=params)
        response.raise_for_status()
    data = response.json()
    return list(data.get("results", []))[:limit]


def _pre_score(req: HuntRequest, title: str, snippet: str, url: str) -> tuple[int, list[str]]:
    haystack = f"{title} {snippet} {url}".lower()
    score = 20
    reasons: list[str] = []
    region_tokens = [x.strip().lower() for x in req.region.replace(",", " ").split() if len(x.strip()) > 3]
    if any(token in haystack for token in region_tokens):
        score += 25
        reasons.append("обнаружено соответствие региону")
    if any(x in haystack for x in ["каталог", "товар", "оборудован", "услуг", "подбор", "расчет", "заказать"]):
        score += 20
        reasons.append("есть признаки коммерческого каталога или сложного выбора")
    if any(x in haystack for x in ["опт", "производ", "монтаж", "проект", "комплектац", "прайс"]):
        score += 15
        reasons.append("есть признаки содержательной коммерческой задачи")
    if _domain(url).endswith(".ru"):
        score += 5
    return min(score, 100), reasons


async def run_hunt(req: HuntRequest) -> HuntResult:
    queries = _build_queries(req)
    raw_results: list[dict] = []
    for query in queries:
        try:
            raw_results.extend(await _search_searxng(query, req.results_per_query))
        except Exception as exc:
            if not raw_results:
                return HuntResult(
                    region=req.region,
                    search_zone=req.search_zone,
                    queries=queries,
                    discovered=0,
                    candidates=[],
                    notes=[f"Поиск не выполнен: {exc}"],
                )

    unique: dict[str, dict] = {}
    for item in raw_results:
        url = str(item.get("url") or "")
        host = _domain(url)
        if not host or host in EXCLUDED_HOSTS or any(host.endswith(f".{x}") for x in EXCLUDED_HOSTS):
            continue
        unique.setdefault(host, item)
        if len(unique) >= req.max_candidates:
            break

    async def inspect(item: dict) -> HuntCandidate | None:
        url = str(item.get("url") or "")
        title = str(item.get("title") or _domain(url))
        snippet = str(item.get("content") or item.get("snippet") or "")
        pre_score, reasons = _pre_score(req, title, snippet, url)
        if pre_score < req.minimum_pre_score:
            return None
        try:
            page = await fetch_site(url)
            analysis = heuristic_analysis(page["final_url"], page["title"], page["text"])
            regional_text = f'{page["title"]} {page["text"][:12000]}'.lower()
            region_confirmed = any(token in regional_text for token in req.region.lower().split() if len(token) > 3)
            final_score = round((pre_score + analysis.commercial_opportunity.score) / 2)
            if not region_confirmed:
                final_score = max(0, final_score - 20)
                reasons.append("региональная принадлежность требует проверки")
            return HuntCandidate(
                company_name=analysis.company_name,
                url=analysis.url,
                source_title=title,
                source_snippet=snippet[:500],
                region_confirmed=region_confirmed,
                preliminary_score=pre_score,
                final_score=final_score,
                qualification=analysis.commercial_opportunity.qualification,
                business_summary=analysis.business_summary,
                recommended_solution=analysis.commercial_opportunity.recommended_solution,
                reasons=reasons,
                analysis=analysis if final_score >= req.deep_audit_score else None,
            )
        except (FetchError, httpx.HTTPError, ValueError):
            return None

    semaphore = asyncio.Semaphore(req.concurrency)

    async def guarded(item: dict) -> HuntCandidate | None:
        async with semaphore:
            return await inspect(item)

    inspected = await asyncio.gather(*(guarded(item) for item in unique.values()))
    candidates = [x for x in inspected if x is not None]
    candidates.sort(key=lambda x: x.final_score, reverse=True)
    return HuntResult(
        region=req.region,
        search_zone=req.search_zone,
        queries=queries,
        discovered=len(unique),
        candidates=candidates[: req.output_limit],
        notes=[
            "Поиск, дедупликация, предварительная фильтрация и ранжирование выполнены автоматически.",
            "Глубокий пакет коммерческой возможности сохранён только для целей, прошедших порог deep_audit_score.",
        ],
    )
