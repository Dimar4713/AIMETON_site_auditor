from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from app.heuristics import heuristic_analysis
from app.llm import analyze_with_routerai
from app.models import CompanyIntelligenceRequest, CompanyIntelligenceResult, EvidenceSource, IntelligenceSource, SiteAnalysis
from app.scraper import FetchError, fetch_site


HOST_CLASSES = {
    "registry": {"companies.rbc.ru", "rusprofile.ru", "www.rusprofile.ru", "checko.ru", "www.checko.ru", "list-org.com", "www.list-org.com", "audit-it.ru", "www.audit-it.ru", "egrul.nalog.ru", "bo.nalog.ru"},
    "finance": {"bo.nalog.ru", "audit-it.ru", "www.audit-it.ru", "companies.rbc.ru", "checko.ru", "www.checko.ru"},
    "workforce": {"hh.ru", "www.hh.ru", "superjob.ru", "www.superjob.ru", "zarplata.ru", "www.zarplata.ru"},
    "contact": {"2gis.ru", "www.2gis.ru", "yandex.ru", "www.yandex.ru"},
    "review": {"flamp.ru", "www.flamp.ru", "zoon.ru", "www.zoon.ru", "otzovik.com", "www.otzovik.com", "irecommend.ru", "www.irecommend.ru"},
    "social": {"vk.com", "www.vk.com", "ok.ru", "www.ok.ru", "t.me", "telegram.me", "youtube.com", "www.youtube.com", "rutube.ru", "www.rutube.ru", "dzen.ru", "www.dzen.ru"},
    "tender": {"zakupki.gov.ru", "www.zakupki.gov.ru", "rostender.info", "www.rostender.info", "b2b-center.ru", "www.b2b-center.ru"},
    "patent": {"new.fips.ru", "fips.ru", "www.fips.ru", "patents.google.com"},
    "court": {"sudrf.ru", "www.sudrf.ru", "mos-gorsud.ru", "www.mos-gorsud.ru", "sudact.ru", "www.sudact.ru"},
    "arbitration": {"kad.arbitr.ru", "arbitr.ru", "www.arbitr.ru", "ras.arbitr.ru"},
    "enforcement": {"fssp.gov.ru", "www.fssp.gov.ru", "bankrot.fedresurs.ru", "fedresurs.ru", "www.fedresurs.ru"},
}
NEWS_MARKERS = ("news", "vedomosti", "kommersant", "rbc.ru", "tass.ru", "ria.ru", "interfax", "ngs.ru")


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def _classify_source(url: str, official_host: str | None, query_kind: str | None = None) -> str:
    host = _host(url)
    if official_host and (host == official_host or host.endswith(f".{official_host}")):
        return "official"
    if query_kind:
        return query_kind
    for source_class, hosts in HOST_CLASSES.items():
        if host in hosts:
            return source_class
    if any(marker in host for marker in NEWS_MARKERS):
        return "news"
    return "other"


def _evidence_level(source_class: str) -> str:
    if source_class == "official":
        return "confirmed_fact"
    if source_class in {"registry", "finance", "court", "arbitration", "enforcement", "news", "tender", "patent"}:
        return "corroborated_signal"
    if source_class in {"ownership", "affiliation", "workforce", "contact", "review", "social", "jobs"}:
        return "weak_signal"
    return "unverified_mention"


def _source_type(source_class: str) -> str:
    return {
        "official": "official_page", "registry": "registry", "court": "court",
        "arbitration": "arbitration", "enforcement": "enforcement",
        "ownership": "ownership", "affiliation": "affiliation", "finance": "finance",
        "workforce": "workforce", "contact": "contact", "news": "news", "social": "social",
        "review": "review", "jobs": "jobs", "tender": "tender", "patent": "patent",
    }.get(source_class, "external_source")


async def _search(query: str, limit: int) -> list[dict]:
    base_url = os.getenv("SEARXNG_BASE_URL")
    if not base_url:
        return []
    params = {"q": query, "format": "json", "language": "ru-RU", "safesearch": 1}
    async with httpx.AsyncClient(timeout=35, follow_redirects=True) as client:
        response = await client.get(f"{base_url.rstrip('/')}/search", params=params)
        response.raise_for_status()
    return list(response.json().get("results", []))[:limit]


def _query_plan(company_name: str, region: str | None = None) -> list[tuple[str, str]]:
    suffix = f" {region}" if region else ""
    q = company_name
    return [
        ("official", f'"{q}" официальный сайт{suffix}'),
        ("contact", f'"{q}" телефон email адрес контакты{suffix}'),
        ("contact", f'"{q}" филиалы офисы представительства география'),
        ("registry", f'"{q}" ИНН ОГРН выписка ЕГРЮЛ{suffix}'),
        ("finance", f'"{q}" выручка прибыль активы налоги бухгалтерская отчетность'),
        ("finance", f'"{q}" оборот финансовые показатели 2024 2025'),
        ("workforce", f'"{q}" численность сотрудников среднесписочная численность'),
        ("jobs", f'"{q}" вакансии работодатель команда сотрудники'),
        ("ownership", f'"{q}" учредитель генеральный директор владелец бенефициар'),
        ("ownership", f'"{q}" конечный бенефициар фактический владелец доля участия'),
        ("affiliation", f'"{q}" аффилированные лица связанные компании группа компаний'),
        ("affiliation", f'"{q}" общий учредитель директор адрес телефон домен'),
        ("arbitration", f'"{q}" site:kad.arbitr.ru OR site:arbitr.ru'),
        ("arbitration", f'"{q}" арбитражный суд истец ответчик дело'),
        ("court", f'"{q}" суд иск решение взыскание'),
        ("enforcement", f'"{q}" ФССП исполнительное производство задолженность'),
        ("enforcement", f'"{q}" банкротство Федресурс сообщение кредитор'),
        ("news", f'"{q}" новости{suffix}'),
        ("review", f'"{q}" отзывы клиентов{suffix}'),
        ("social", f'"{q}" site:vk.com OR site:t.me OR site:ok.ru'),
        ("tender", f'"{q}" тендер OR закупка OR контракт'),
        ("patent", f'"{q}" патент OR изобретение'),
        ("other", f'"{q}" продукция услуги клиенты партнеры поставщики'),
        ("other", f'"{q}" оборудование производство мощности технологии автоматизация'),
        ("other", f'"{q}" руководство стратегия развитие сертификаты лицензии'),
    ]


async def collect_external_sources(company_name: str, official_url: str | None, region: str | None = None, max_sources: int = 60) -> tuple[list[IntelligenceSource], list[str]]:
    if not os.getenv("SEARXNG_BASE_URL"):
        return [], ["SEARXNG_BASE_URL не задан: внешний OSINT-контур не выполнен."]
    notes: list[str] = []
    plan = _query_plan(company_name, region)
    per_query = max(2, min(5, max_sources // max(1, len(plan)) + 1))
    semaphore = asyncio.Semaphore(6)

    async def run(kind: str, query: str):
        async with semaphore:
            try:
                return kind, query, await _search(query, per_query), None
            except httpx.HTTPError as exc:
                return kind, query, [], str(exc)

    batches = await asyncio.gather(*(run(kind, query) for kind, query in plan))
    raw: list[dict] = []
    for kind, query, items, error in batches:
        if error:
            notes.append(f"Часть поиска недоступна для запроса {query!r}: {error}")
        for item in items:
            item = dict(item)
            item["_query_kind"] = kind
            item["_query"] = query
            raw.append(item)

    official_host = _host(official_url or "") or None
    accessed_at = datetime.now(timezone.utc).isoformat()
    seen: set[str] = set()
    sources: list[IntelligenceSource] = []
    for item in raw:
        url = str(item.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        query_kind = str(item.get("_query_kind") or "") or None
        source_class = _classify_source(url, official_host, query_kind)
        snippet = str(item.get("content") or item.get("snippet") or "")[:900]
        sources.append(IntelligenceSource(
            id=f"E{len(sources) + 1}", title=str(item.get("title") or _host(url) or url)[:300],
            url=url, snippet=snippet, accessed_at=accessed_at,
            source_class=source_class, evidence_level=_evidence_level(source_class),
        ))
        if len(sources) >= max_sources:
            break
    return sources, notes


def _to_llm_sources(sources: list[IntelligenceSource]) -> list[dict]:
    return [{
        "id": s.id, "title": s.title, "url": s.url, "snippet": s.snippet,
        "accessed_at": s.accessed_at, "source_class": s.source_class,
        "source_type": _source_type(s.source_class), "evidence_level": s.evidence_level,
    } for s in sources]


async def run_enriched_site_analysis(url: str, title: str, text: str) -> SiteAnalysis:
    company_hint = title.split("—")[0].split("|")[0].strip() or _host(url)
    external_sources, notes = await collect_external_sources(company_hint, url, max_sources=60)
    try:
        analysis = await analyze_with_routerai(url, title, text, _to_llm_sources(external_sources))
    except Exception as exc:
        analysis = heuristic_analysis(url, title, text)
        analysis.risks_and_assumptions.append(f"Использован резервный локальный анализ: {type(exc).__name__}.")

    known = {source.id for source in analysis.sources}
    for item in external_sources:
        if item.id in known:
            continue
        analysis.sources.append(EvidenceSource(
            id=item.id, title=item.title, url=item.url, accessed_at=item.accessed_at,
            evidence_quote=item.snippet or "Поисковый результат без сниппета; требуется ручная проверка.",
            source_type=_source_type(item.source_class), evidence_level=item.evidence_level,
        ))
        known.add(item.id)

    counts: dict[str, int] = {}
    for source in external_sources:
        counts[source.source_class] = counts.get(source.source_class, 0) + 1
    if counts:
        analysis.risks_and_assumptions.append(
            "Внешний OSINT-контур: " + ", ".join(f"{kind}={count}" for kind, count in sorted(counts.items())) + ". Сниппеты требуют перехода к первоисточнику."
        )
    analysis.risks_and_assumptions.extend(notes)
    analysis.risks_and_assumptions.append(
        "Матрица 4×4 — техническая проекция бизнес-машины по КМ: I коммуникации, II люди, III технологии, IV менеджмент; измерения — внешний контур, внутренний контур, ресурсы/масштаб, результат/риски. Пустая ячейка означает отсутствие подтвержденных данных, а не отсутствие функции."
    )
    return analysis


async def _analyze_site(url: str) -> SiteAnalysis:
    page = await fetch_site(url)
    return await run_enriched_site_analysis(page["final_url"], page["title"], page["text"])


async def run_company_intelligence(req: CompanyIntelligenceRequest) -> CompanyIntelligenceResult:
    notes: list[str] = []
    official_url = str(req.url) if req.url else None
    sources, search_notes = await collect_external_sources(req.company_name, official_url, req.region, req.max_sources)
    notes.extend(search_notes)
    if not official_url:
        official = next((s for s in sources if s.source_class == "official"), None)
        official_url = official.url if official else None
    site_analysis = None
    if official_url:
        try:
            site_analysis = await _analyze_site(official_url)
            official_url = site_analysis.url
        except (FetchError, httpx.HTTPError, ValueError) as exc:
            notes.append(f"Официальный сайт не удалось глубоко проанализировать: {exc}")
    counts = {kind: sum(1 for source in sources if source.source_class == kind) for kind in {s.source_class for s in sources}}
    scent_summary = [f"{kind}: {count}" for kind, count in sorted(counts.items())]
    if site_analysis:
        scent_summary.extend(signal.signal for signal in site_analysis.economic_signals[:5])
    score = site_analysis.commercial_opportunity.score if site_analysis else min(60, 20 + len(sources) * 2)
    solution = site_analysis.commercial_opportunity.recommended_solution if site_analysis else "Требуется глубокий анализ официального сайта и перекрестная проверка источников."
    return CompanyIntelligenceResult(
        company_name=site_analysis.company_name if site_analysis else req.company_name,
        region=req.region, official_url=official_url, site_analysis=site_analysis,
        sources=sources, scent_summary=scent_summary, confidence_notes=notes,
        commercial_score=score, recommended_solution=solution,
        status="complete" if site_analysis and sources else "partial",
    )
