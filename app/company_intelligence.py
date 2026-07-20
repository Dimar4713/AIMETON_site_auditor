from __future__ import annotations

import os
from urllib.parse import urlparse

import httpx

from app.heuristics import heuristic_analysis
from app.llm import analyze_with_routerai
from app.models import (
    CompanyIntelligenceRequest,
    CompanyIntelligenceResult,
    IntelligenceSource,
    SiteAnalysis,
)
from app.scraper import FetchError, fetch_site


DIRECTORY_HOSTS = {
    "companies.rbc.ru",
    "rusprofile.ru",
    "www.rusprofile.ru",
    "2gis.ru",
    "www.2gis.ru",
    "yandex.ru",
    "www.yandex.ru",
}
REVIEW_HOSTS = {
    "flamp.ru",
    "www.flamp.ru",
    "prodoctorov.ru",
    "www.prodoctorov.ru",
    "zoon.ru",
    "www.zoon.ru",
}
JOBS_HOSTS = {"hh.ru", "www.hh.ru", "superjob.ru", "www.superjob.ru"}
NEWS_MARKERS = ("news", "vedomosti", "kommersant", "rbc.ru", "tass.ru", "ria.ru")


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def _classify_source(url: str, official_host: str | None) -> str:
    host = _host(url)
    if official_host and (host == official_host or host.endswith(f".{official_host}")):
        return "official"
    if host in DIRECTORY_HOSTS:
        return "directory"
    if host in REVIEW_HOSTS:
        return "review"
    if host in JOBS_HOSTS:
        return "jobs"
    if any(marker in host for marker in NEWS_MARKERS):
        return "news"
    return "other"


def _evidence_level(source_class: str) -> str:
    if source_class == "official":
        return "confirmed_fact"
    if source_class in {"directory", "news"}:
        return "corroborated_signal"
    if source_class in {"review", "jobs"}:
        return "weak_signal"
    return "unverified_mention"


async def _search(query: str, limit: int) -> list[dict]:
    base_url = os.getenv("SEARXNG_BASE_URL")
    if not base_url:
        return []
    params = {"q": query, "format": "json", "language": "ru-RU"}
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.get(f"{base_url.rstrip('/')}/search", params=params)
        response.raise_for_status()
    return list(response.json().get("results", []))[:limit]


async def _analyze_site(url: str) -> SiteAnalysis:
    page = await fetch_site(url)
    try:
        return await analyze_with_routerai(page["final_url"], page["title"], page["text"])
    except Exception:
        analysis = heuristic_analysis(page["final_url"], page["title"], page["text"])
        analysis.risks_and_assumptions.append(
            "Использован резервный локальный анализ; LLM была недоступна или вернула невалидный ответ."
        )
        return analysis


async def run_company_intelligence(req: CompanyIntelligenceRequest) -> CompanyIntelligenceResult:
    notes: list[str] = []
    site_analysis: SiteAnalysis | None = None
    official_url = str(req.url) if req.url else None

    queries = [
        f'"{req.company_name}" официальный сайт {req.region or ""}'.strip(),
        f'"{req.company_name}" новости {req.region or ""}'.strip(),
        f'"{req.company_name}" отзывы'.strip(),
        f'"{req.company_name}" ИНН ОГРН выручка'.strip(),
        f'"{req.company_name}" вакансии'.strip(),
    ]

    raw: list[dict] = []
    per_query = max(3, req.max_sources // len(queries))
    for query in queries:
        try:
            raw.extend(await _search(query, per_query))
        except httpx.HTTPError as exc:
            notes.append(f"Поисковый источник частично недоступен: {exc}")

    if not official_url:
        for item in raw:
            candidate = str(item.get("url") or "")
            host = _host(candidate)
            if not host or host in DIRECTORY_HOSTS | REVIEW_HOSTS | JOBS_HOSTS:
                continue
            title = str(item.get("title") or "").lower()
            if "официаль" in title or req.company_name.lower().split()[0] in host:
                official_url = candidate
                break

    if official_url:
        try:
            site_analysis = await _analyze_site(official_url)
            official_url = site_analysis.url
        except (FetchError, httpx.HTTPError, ValueError) as exc:
            notes.append(f"Официальный сайт не удалось глубоко проанализировать: {exc}")

    official_host = _host(official_url) if official_url else None
    sources: list[IntelligenceSource] = []
    seen: set[str] = set()
    for item in raw:
        url = str(item.get("url") or "")
        if not url or url in seen:
            continue
        seen.add(url)
        source_class = _classify_source(url, official_host)
        sources.append(
            IntelligenceSource(
                title=str(item.get("title") or _host(url)),
                url=url,
                snippet=str(item.get("content") or item.get("snippet") or "")[:700],
                source_class=source_class,
                evidence_level=_evidence_level(source_class),
            )
        )
        if len(sources) >= req.max_sources:
            break

    scent_summary: list[str] = []
    counts = {kind: sum(1 for source in sources if source.source_class == kind) for kind in {
        "official", "news", "directory", "review", "jobs", "other"
    }}
    if counts["news"]:
        scent_summary.append(f"Обнаружен новостной фон: {counts['news']} публикаций или упоминаний.")
    if counts["review"]:
        scent_summary.append(f"Обнаружен клиентский фон: {counts['review']} источников отзывов и обсуждений.")
    if counts["directory"]:
        scent_summary.append(f"Юридический/справочный профиль представлен в {counts['directory']} источниках.")
    if counts["jobs"]:
        scent_summary.append(f"Есть кадровые сигналы: {counts['jobs']} источников вакансий или работодателя.")
    if site_analysis:
        scent_summary.extend(signal.signal for signal in site_analysis.economic_signals[:5])

    if not os.getenv("SEARXNG_BASE_URL"):
        notes.append("SEARXNG_BASE_URL не задан: новостной и внешний OSINT-контур не выполнен.")

    score = site_analysis.commercial_opportunity.score if site_analysis else min(60, 20 + len(sources) * 2)
    solution = (
        site_analysis.commercial_opportunity.recommended_solution
        if site_analysis
        else "Требуется глубокий анализ официального сайта и перекрёстная проверка внешних источников."
    )
    status = "complete" if site_analysis and sources and os.getenv("SEARXNG_BASE_URL") else "partial"

    return CompanyIntelligenceResult(
        company_name=site_analysis.company_name if site_analysis else req.company_name,
        region=req.region,
        official_url=official_url,
        site_analysis=site_analysis,
        sources=sources,
        scent_summary=scent_summary,
        confidence_notes=notes,
        commercial_score=score,
        recommended_solution=solution,
        status=status,
    )
