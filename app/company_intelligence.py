from __future__ import annotations

import os
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from app.heuristics import heuristic_analysis
from app.llm import analyze_with_routerai
from app.models import (
    CompanyIntelligenceRequest,
    CompanyIntelligenceResult,
    EvidenceSource,
    IntelligenceSource,
    SiteAnalysis,
)
from app.scraper import FetchError, fetch_site


DIRECTORY_HOSTS = {
    "companies.rbc.ru", "rusprofile.ru", "www.rusprofile.ru", "2gis.ru", "www.2gis.ru",
    "yandex.ru", "www.yandex.ru", "checko.ru", "www.checko.ru", "list-org.com", "www.list-org.com",
}
REVIEW_HOSTS = {
    "flamp.ru", "www.flamp.ru", "prodoctorov.ru", "www.prodoctorov.ru", "zoon.ru", "www.zoon.ru",
    "otzovik.com", "www.otzovik.com", "irecommend.ru", "www.irecommend.ru",
}
JOBS_HOSTS = {"hh.ru", "www.hh.ru", "superjob.ru", "www.superjob.ru", "zarplata.ru", "www.zarplata.ru"}
SOCIAL_HOSTS = {
    "vk.com", "www.vk.com", "ok.ru", "www.ok.ru", "t.me", "telegram.me", "youtube.com", "www.youtube.com",
    "rutube.ru", "www.rutube.ru", "dzen.ru", "www.dzen.ru",
}
TENDER_HOSTS = {
    "zakupki.gov.ru", "www.zakupki.gov.ru", "rostender.info", "www.rostender.info", "b2b-center.ru", "www.b2b-center.ru",
}
PATENT_HOSTS = {"new.fips.ru", "fips.ru", "www.fips.ru", "patents.google.com"}
NEWS_MARKERS = ("news", "vedomosti", "kommersant", "rbc.ru", "tass.ru", "ria.ru", "interfax", "ngs.ru")


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def _classify_source(url: str, official_host: str | None) -> str:
    host = _host(url)
    if official_host and (host == official_host or host.endswith(f".{official_host}")):
        return "official"
    if host in SOCIAL_HOSTS:
        return "social"
    if host in REVIEW_HOSTS:
        return "review"
    if host in JOBS_HOSTS:
        return "jobs"
    if host in TENDER_HOSTS:
        return "tender"
    if host in PATENT_HOSTS:
        return "patent"
    if host in DIRECTORY_HOSTS:
        return "registry"
    if any(marker in host for marker in NEWS_MARKERS):
        return "news"
    return "other"


def _evidence_level(source_class: str) -> str:
    if source_class == "official":
        return "confirmed_fact"
    if source_class in {"registry", "news", "tender", "patent"}:
        return "corroborated_signal"
    if source_class in {"review", "jobs", "social"}:
        return "weak_signal"
    return "unverified_mention"


def _source_type(source_class: str) -> str:
    mapping = {
        "official": "official_page",
        "registry": "registry",
        "news": "news",
        "social": "social",
        "review": "review",
        "jobs": "jobs",
        "tender": "tender",
        "patent": "patent",
    }
    return mapping.get(source_class, "external_source")


async def _search(query: str, limit: int) -> list[dict]:
    base_url = os.getenv("SEARXNG_BASE_URL")
    if not base_url:
        return []
    params = {"q": query, "format": "json", "language": "ru-RU", "safesearch": 1}
    async with httpx.AsyncClient(timeout=35, follow_redirects=True) as client:
        response = await client.get(f"{base_url.rstrip('/')}/search", params=params)
        response.raise_for_status()
    return list(response.json().get("results", []))[:limit]


def _query_plan(company_name: str, region: str | None = None) -> list[str]:
    suffix = f" {region}" if region else ""
    return [
        f'"{company_name}" официальный сайт{suffix}',
        f'"{company_name}" ИНН ОГРН руководитель{suffix}',
        f'"{company_name}" новости{suffix}',
        f'"{company_name}" отзывы{suffix}',
        f'"{company_name}" вакансии',
        f'"{company_name}" site:vk.com OR site:t.me OR site:ok.ru',
        f'"{company_name}" тендер OR закупка OR контракт',
        f'"{company_name}" патент OR изобретение',
    ]


async def collect_external_sources(
    company_name: str,
    official_url: str | None,
    region: str | None = None,
    max_sources: int = 30,
) -> tuple[list[IntelligenceSource], list[str]]:
    notes: list[str] = []
    if not os.getenv("SEARXNG_BASE_URL"):
        return [], ["SEARXNG_BASE_URL не задан: внешний OSINT-контур не выполнен."]

    raw: list[dict] = []
    queries = _query_plan(company_name, region)
    per_query = max(3, min(8, max_sources // max(1, len(queries)) + 1))
    for query in queries:
        try:
            raw.extend(await _search(query, per_query))
        except httpx.HTTPError as exc:
            notes.append(f"Часть внешнего поиска недоступна для запроса {query!r}: {exc}")

    official_host = _host(official_url or "") or None
    accessed_at = datetime.now(timezone.utc).isoformat()
    seen_urls: set[str] = set()
    sources: list[IntelligenceSource] = []
    for item in raw:
        url = str(item.get("url") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        source_class = _classify_source(url, official_host)
        sources.append(IntelligenceSource(
            id=f"E{len(sources) + 1}",
            title=str(item.get("title") or _host(url) or url)[:300],
            url=url,
            snippet=str(item.get("content") or item.get("snippet") or "")[:700],
            accessed_at=accessed_at,
            source_class=source_class,
            evidence_level=_evidence_level(source_class),
        ))
        if len(sources) >= max_sources:
            break
    return sources, notes


def _to_llm_sources(sources: list[IntelligenceSource]) -> list[dict]:
    return [
        {
            "id": source.id,
            "title": source.title,
            "url": source.url,
            "snippet": source.snippet,
            "accessed_at": source.accessed_at,
            "source_class": source.source_class,
            "source_type": _source_type(source.source_class),
            "evidence_level": source.evidence_level,
        }
        for source in sources
    ]


async def run_enriched_site_analysis(url: str, title: str, text: str) -> SiteAnalysis:
    company_hint = title.split("—")[0].split("|")[0].strip() or _host(url)
    external_sources, notes = await collect_external_sources(company_hint, url, max_sources=30)
    try:
        analysis = await analyze_with_routerai(url, title, text, _to_llm_sources(external_sources))
    except Exception:
        analysis = heuristic_analysis(url, title, text)
        analysis.risks_and_assumptions.append(
            "Использован резервный локальный анализ; LLM была недоступна или вернула невалидный ответ."
        )

    known = {source.id for source in analysis.sources}
    for item in external_sources:
        if item.id in known:
            continue
        analysis.sources.append(EvidenceSource(
            id=item.id,
            title=item.title,
            url=item.url,
            accessed_at=item.accessed_at,
            evidence_quote=item.snippet or "Поисковый результат без сниппета; требуется ручная проверка страницы.",
            source_type=_source_type(item.source_class),
            evidence_level=item.evidence_level,
        ))
        known.add(item.id)

    if external_sources:
        counts: dict[str, int] = {}
        for source in external_sources:
            counts[source.source_class] = counts.get(source.source_class, 0) + 1
        summary = ", ".join(f"{kind}: {count}" for kind, count in sorted(counts.items()))
        analysis.risks_and_assumptions.append(
            f"Внешний OSINT-контур собрал {len(external_sources)} источников ({summary}). Поисковые сниппеты требуют перехода к первоисточнику для окончательной проверки."
        )
    else:
        analysis.risks_and_assumptions.append("Внешние источники не найдены или поисковый контур недоступен.")
    analysis.risks_and_assumptions.extend(notes)
    return analysis


async def _analyze_site(url: str) -> SiteAnalysis:
    page = await fetch_site(url)
    return await run_enriched_site_analysis(page["final_url"], page["title"], page["text"])


async def run_company_intelligence(req: CompanyIntelligenceRequest) -> CompanyIntelligenceResult:
    notes: list[str] = []
    site_analysis: SiteAnalysis | None = None
    official_url = str(req.url) if req.url else None

    sources, search_notes = await collect_external_sources(
        req.company_name,
        official_url,
        req.region,
        req.max_sources,
    )
    notes.extend(search_notes)

    if not official_url:
        for source in sources:
            if source.source_class == "official":
                official_url = source.url
                break
        if not official_url:
            for source in sources:
                host = _host(source.url)
                if source.source_class not in {"registry", "review", "jobs", "social", "tender", "patent"} and host:
                    official_url = source.url
                    break

    if official_url:
        try:
            site_analysis = await _analyze_site(official_url)
            official_url = site_analysis.url
        except (FetchError, httpx.HTTPError, ValueError) as exc:
            notes.append(f"Официальный сайт не удалось глубоко проанализировать: {exc}")

    scent_summary: list[str] = []
    classes = {source.source_class for source in sources}
    counts = {kind: sum(1 for source in sources if source.source_class == kind) for kind in classes}
    labels = {
        "news": "новостных публикаций",
        "review": "источников отзывов",
        "registry": "реестровых/справочных источников",
        "jobs": "кадровых источников",
        "social": "социальных площадок",
        "tender": "тендерных источников",
        "patent": "патентных источников",
    }
    for kind, label in labels.items():
        if counts.get(kind):
            scent_summary.append(f"Обнаружено {counts[kind]} {label}.")
    if site_analysis:
        scent_summary.extend(signal.signal for signal in site_analysis.economic_signals[:5])

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
