from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from app.heuristics import heuristic_analysis
from app.hunter_handbook import OPPORTUNITY_PATTERNS, resolve_industries
from app.models import HuntCandidate, HuntRequest, HuntResult
from app.scraper import FetchError, fetch_site


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

COMMERCIAL_MARKERS = ("каталог", "товар", "оборудован", "услуг", "подбор", "расчет", "заказать")
COMPLEXITY_MARKERS = ("опт", "производ", "монтаж", "проект", "комплектац", "прайс")


@dataclass(frozen=True)
class PreScoreResult:
    score: int | None
    status: str
    factors: dict[str, int | None]
    reasons: list[str]


def _domain(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def _build_queries(req: HuntRequest) -> list[str]:
    selected = resolve_industries(req.industries)
    queries: list[str] = []
    seen: set[str] = set()

    def add(query: str) -> None:
        normalized = " ".join(query.split())
        if normalized and normalized not in seen and len(queries) < req.max_queries:
            seen.add(normalized)
            queries.append(normalized)

    for industry in selected:
        variants = [industry["name"], *industry["aliases"]]
        for variant in variants[:4]:
            add(f'{variant} {req.region} официальный сайт компания')
            if req.search_zone:
                add(f'{variant} {req.search_zone} официальный сайт')

        for signal_id in industry.get("signals", [])[:3]:
            signal = OPPORTUNITY_PATTERNS.get(signal_id, signal_id)
            add(f'{industry["name"]} {signal} {req.region} компания')

    for focus in req.focus:
        add(f'{focus} {req.region} компания официальный сайт')

    return queries


async def _search_searxng(query: str, limit: int) -> list[dict]:
    base_url = os.getenv("SEARXNG_BASE_URL")
    if not base_url:
        raise RuntimeError("SEARXNG_BASE_URL не задан")
    params = {"q": query, "format": "json", "language": "ru-RU"}
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.get(f"{base_url.rstrip('/')}/search", params=params)
        response.raise_for_status()
    return list(response.json().get("results", []))[:limit]


def _pre_score(req: HuntRequest, title: str, snippet: str, url: str) -> PreScoreResult:
    host = _domain(url)
    title = title.strip()
    snippet = snippet.strip()
    factors: dict[str, int | None] = {
        "region_match": None,
        "commercial_choice": None,
        "commercial_complexity": None,
        "focus_match": None,
        "local_domain": None,
    }
    reasons: list[str] = []

    if not host or not (title or snippet):
        reasons.append("недостаточно данных: отсутствует домен либо текст поискового результата")
        return PreScoreResult(None, "insufficient_data", factors, reasons)

    haystack = f"{title} {snippet} {url}".lower()
    region_tokens = [token for token in req.region.replace(",", " ").lower().split() if len(token) > 3]
    if region_tokens:
        factors["region_match"] = 25 if any(token in haystack for token in region_tokens) else 0
        if factors["region_match"]:
            reasons.append("обнаружено соответствие территории охоты")

    factors["commercial_choice"] = 20 if any(marker in haystack for marker in COMMERCIAL_MARKERS) else 0
    if factors["commercial_choice"]:
        reasons.append("есть признаки коммерческого каталога или сложного выбора")

    factors["commercial_complexity"] = 15 if any(marker in haystack for marker in COMPLEXITY_MARKERS) else 0
    if factors["commercial_complexity"]:
        reasons.append("есть признаки содержательной коммерческой задачи")

    if req.focus:
        factors["focus_match"] = 10 if any(focus.lower() in haystack for focus in req.focus) else 0
        if factors["focus_match"]:
            reasons.append("обнаружено соответствие заданному фокусу охоты")

    factors["local_domain"] = 5 if host.endswith(".ru") else 0
    if factors["local_domain"]:
        reasons.append("используется домен российской зоны")

    score = 20 + sum(value for value in factors.values() if value is not None)
    return PreScoreResult(min(score, 100), "calculated", factors, reasons)


def _shallow_candidate(
    title: str,
    snippet: str,
    url: str,
    result: PreScoreResult,
    *,
    qualification: str,
    summary: str,
    recommendation: str,
) -> HuntCandidate:
    return HuntCandidate(
        company_name=title or _domain(url),
        url=url,
        source_title=title,
        source_snippet=snippet[:500],
        region_confirmed=None,
        preliminary_score=result.score,
        pre_score_status=result.status,
        pre_score_factors=result.factors,
        deep_analysis_performed=False,
        final_score=result.score,
        qualification=qualification,
        business_summary=summary,
        recommended_solution=recommendation,
        reasons=result.reasons,
        analysis=None,
    )


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
        if not host or host in EXCLUDED_HOSTS or any(host.endswith(f".{excluded}") for excluded in EXCLUDED_HOSTS):
            continue
        unique.setdefault(host, item)
        if len(unique) >= req.max_candidates:
            break

    async def inspect(item: dict) -> HuntCandidate | None:
        url = str(item.get("url") or "")
        title = str(item.get("title") or _domain(url))
        snippet = str(item.get("content") or item.get("snippet") or "")
        result = _pre_score(req, title, snippet, url)

        if result.status == "insufficient_data":
            return _shallow_candidate(
                title,
                snippet,
                url,
                result,
                qualification="Недостаточно данных",
                summary="Pre-score не рассчитан: поисковый результат не содержит достаточных признаков.",
                recommendation="Уточнить поисковый результат или получить первичный документ до глубокой разведки.",
            )

        assert result.score is not None
        if result.score < req.minimum_pre_score:
            return None

        if result.score < req.deep_audit_score:
            return _shallow_candidate(
                title,
                snippet,
                url,
                result,
                qualification="Наблюдение",
                summary="Кандидат прошёл минимальный pre-score, но не достиг порога глубокой разведки.",
                recommendation="Сохранить в наблюдении и усилить признаки до запуска глубокой обработки.",
            )

        try:
            page = await fetch_site(url)
            analysis = heuristic_analysis(page["final_url"], page["title"], page["text"])
            regional_text = f'{page["title"]} {page["text"][:12000]}'.lower()
            region_tokens = [token for token in req.region.lower().split() if len(token) > 3]
            region_confirmed = any(token in regional_text for token in region_tokens)
            final_score = round((result.score + analysis.commercial_opportunity.score) / 2)
            reasons = list(result.reasons)
            if not region_confirmed:
                final_score = max(0, final_score - 20)
                reasons.append("региональная принадлежность требует проверки")
            return HuntCandidate(
                company_name=analysis.company_name,
                url=analysis.url,
                source_title=title,
                source_snippet=snippet[:500],
                region_confirmed=region_confirmed,
                preliminary_score=result.score,
                pre_score_status=result.status,
                pre_score_factors=result.factors,
                deep_analysis_performed=True,
                final_score=final_score,
                qualification=analysis.commercial_opportunity.qualification,
                business_summary=analysis.business_summary,
                recommended_solution=analysis.commercial_opportunity.recommended_solution,
                reasons=reasons,
                analysis=analysis,
            )
        except (FetchError, httpx.HTTPError, ValueError) as exc:
            fallback = _shallow_candidate(
                title,
                snippet,
                url,
                result,
                qualification="Наблюдение",
                summary="Порог глубокой разведки достигнут, но первичный сайт не удалось обработать.",
                recommendation="Повторить загрузку или проверить сайт вручную.",
            )
            fallback.reasons.append(f"глубокая обработка не выполнена: {type(exc).__name__}")
            return fallback

    semaphore = asyncio.Semaphore(req.concurrency)

    async def guarded(item: dict) -> HuntCandidate | None:
        async with semaphore:
            return await inspect(item)

    inspected = await asyncio.gather(*(guarded(item) for item in unique.values()))
    candidates = [candidate for candidate in inspected if candidate is not None]
    candidates.sort(
        key=lambda candidate: (
            candidate.pre_score_status == "calculated",
            candidate.final_score if candidate.final_score is not None else -1,
            candidate.preliminary_score if candidate.preliminary_score is not None else -1,
        ),
        reverse=True,
    )
    return HuntResult(
        region=req.region,
        search_zone=req.search_zone,
        queries=queries,
        discovered=len(unique),
        candidates=candidates[: req.output_limit],
        notes=[
            "План охоты сформирован по Справочнику охотника.",
            "Каждый кандидат получает объяснимый pre-score либо явный статус insufficient_data.",
            f"Глубокая обработка запускается только при pre-score >= {req.deep_audit_score}.",
            "Количество найденных ссылок не входит в формулу pre-score.",
        ],
    )
