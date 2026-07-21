from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from app.heuristics import heuristic_analysis
from app.llm import analyze_with_routerai
from app.models import EvidenceSource, IntelligenceSource, SiteAnalysis, SourceKind


HOST_CLASSES: dict[str, set[str]] = {
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
    "aggregator": {"spark-interfax.ru", "www.spark-interfax.ru", "sbis.ru", "www.sbis.ru", "companies.rbc.ru"},
}

NEWS_MARKERS = ("news", "vedomosti", "kommersant", "rbc.ru", "tass.ru", "ria.ru", "interfax", "ngs.ru")
RESULT_MARKERS: list[tuple[SourceKind, tuple[str, ...]]] = [
    ("jobs", ("ваканс", "работодатель", "карьера", "работа в компании")),
    ("court", ("суд", "иск", "решение суда", "судебн")),
    ("arbitration", ("арбитраж", "истец", "ответчик", "дело №")),
    ("news", ("новости", "сообщает", "опубликовал", "пресс-релиз")),
    ("registry", ("инн", "огрн", "егрюл", "регистрац")),
    ("finance", ("выручка", "прибыль", "бухгалтерская отчетность", "финансовые показатели")),
    ("contact", ("телефон", "email", "адрес", "контакты")),
    ("official", ("официальный сайт", "официальная страница")),
]


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def classify_source_domain(url: str, official_host: str | None) -> SourceKind:
    host = _host(url)
    if not host:
        return "unknown"
    if official_host and (host == official_host or host.endswith(f".{official_host}")):
        return "official"
    for source_class, hosts in HOST_CLASSES.items():
        if host in hosts:
            return source_class  # type: ignore[return-value]
    if any(marker in host for marker in NEWS_MARKERS):
        return "news"
    return "unknown"


def classify_result(title: str, snippet: str) -> SourceKind:
    haystack = f"{title} {snippet}".lower()
    matches = [kind for kind, markers in RESULT_MARKERS if any(marker in haystack for marker in markers)]
    if not matches:
        return "unknown"
    if len(set(matches)) > 1:
        return "other"
    return matches[0]


def classification_state(source_class: SourceKind, result_kind: SourceKind) -> str:
    if source_class == "unknown" and result_kind == "unknown":
        return "unknown"
    if source_class not in {"unknown", "aggregator"} and result_kind not in {"unknown", source_class}:
        return "ambiguous"
    return "classified"


def evidence_level(source_class: SourceKind) -> str:
    if source_class == "official":
        return "confirmed_fact"
    if source_class in {"registry", "finance", "court", "arbitration", "enforcement", "news", "tender", "patent"}:
        return "corroborated_signal"
    if source_class in {"ownership", "affiliation", "workforce", "contact", "review", "social", "jobs"}:
        return "weak_signal"
    return "unverified_mention"


def source_type(source_class: SourceKind) -> str:
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


def query_plan(company_name: str, region: str | None = None) -> list[tuple[SourceKind, str]]:
    suffix = f" {region}" if region else ""
    q = company_name
    return [
        ("official", f'"{q}" официальный сайт{suffix}'),
        ("contact", f'"{q}" телефон email адрес контакты{suffix}'),
        ("registry", f'"{q}" ИНН ОГРН выписка ЕГРЮЛ{suffix}'),
        ("finance", f'"{q}" выручка прибыль активы налоги бухгалтерская отчетность'),
        ("workforce", f'"{q}" численность сотрудников среднесписочная численность'),
        ("jobs", f'"{q}" вакансии работодатель команда сотрудники'),
        ("ownership", f'"{q}" учредитель генеральный директор владелец бенефициар'),
        ("affiliation", f'"{q}" аффилированные лица связанные компании группа компаний'),
        ("arbitration", f'"{q}" арбитражный суд истец ответчик дело'),
        ("court", f'"{q}" суд иск решение взыскание'),
        ("enforcement", f'"{q}" ФССП исполнительное производство задолженность'),
        ("news", f'"{q}" новости{suffix}'),
        ("review", f'"{q}" отзывы клиентов{suffix}'),
        ("social", f'"{q}" site:vk.com OR site:t.me OR site:ok.ru'),
        ("tender", f'"{q}" тендер OR закупка OR контракт'),
        ("patent", f'"{q}" патент OR изобретение'),
        ("other", f'"{q}" продукция услуги клиенты партнеры поставщики'),
    ]


async def collect_external_sources(company_name: str, official_url: str | None, region: str | None = None, max_sources: int = 60) -> tuple[list[IntelligenceSource], list[str]]:
    if not os.getenv("SEARXNG_BASE_URL"):
        return [], ["SEARXNG_BASE_URL не задан: внешний OSINT-контур не выполнен."]
    notes: list[str] = []
    plan = query_plan(company_name, region)
    per_query = max(2, min(5, max_sources // max(1, len(plan)) + 1))
    semaphore = asyncio.Semaphore(6)

    async def run(kind: SourceKind, query: str):
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
            copy = dict(item)
            copy["_query_kind"] = kind
            copy["_query"] = query
            raw.append(copy)

    official_host = _host(official_url or "") or None
    accessed_at = datetime.now(timezone.utc).isoformat()
    seen: set[str] = set()
    sources: list[IntelligenceSource] = []
    for item in raw:
        url = str(item.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        title = str(item.get("title") or _host(url) or url)[:300]
        snippet = str(item.get("content") or item.get("snippet") or "")[:900]
        query_kind: SourceKind = item.get("_query_kind") or "unknown"
        source_class = classify_source_domain(url, official_host)
        result_kind = classify_result(title, snippet)
        sources.append(IntelligenceSource(
            id=f"E{len(sources) + 1}", title=title, url=url, snippet=snippet,
            accessed_at=accessed_at, query_kind=query_kind, result_kind=result_kind,
            source_class=source_class,
            classification_state=classification_state(source_class, result_kind),
            evidence_level=evidence_level(source_class),
        ))
        if len(sources) >= max_sources:
            break
    return sources, notes


def to_llm_sources(sources: list[IntelligenceSource]) -> list[dict]:
    return [{
        "id": source.id, "title": source.title, "url": source.url, "snippet": source.snippet,
        "accessed_at": source.accessed_at, "query_kind": source.query_kind,
        "result_kind": source.result_kind, "source_class": source.source_class,
        "classification_state": source.classification_state,
        "source_type": source_type(source.source_class), "evidence_level": source.evidence_level,
    } for source in sources]


async def run_enriched_site_analysis(url: str, title: str, text: str) -> SiteAnalysis:
    company_hint = title.split("—")[0].split("|")[0].strip() or _host(url)
    external_sources, notes = await collect_external_sources(company_hint, url, max_sources=60)
    try:
        analysis = await analyze_with_routerai(url, title, text, to_llm_sources(external_sources))
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
            source_type=source_type(item.source_class), evidence_level=item.evidence_level,
        ))
        known.add(item.id)
    analysis.risks_and_assumptions.extend(notes)
    return analysis
