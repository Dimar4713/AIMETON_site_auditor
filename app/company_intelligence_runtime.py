from __future__ import annotations

import httpx

from app.company_intelligence import (
    _source_type,
    _to_llm_sources,
    collect_external_sources,
)
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


async def _analyze_site_with_sources(
    url: str,
    external_sources: list[IntelligenceSource],
    search_notes: list[str],
) -> SiteAnalysis:
    """Deep-analyze the official site without launching the external search a second time."""
    page = await fetch_site(url)
    try:
        analysis = await analyze_with_routerai(
            page["final_url"],
            page["title"],
            page["text"],
            _to_llm_sources(external_sources),
        )
    except Exception as exc:
        analysis = heuristic_analysis(page["final_url"], page["title"], page["text"])
        analysis.risks_and_assumptions.append(
            f"Использован резервный локальный анализ: {type(exc).__name__}."
        )

    known = {source.id for source in analysis.sources}
    for item in external_sources:
        if item.id in known:
            continue
        analysis.sources.append(
            EvidenceSource(
                id=item.id,
                title=item.title,
                url=item.url,
                accessed_at=item.accessed_at,
                evidence_quote=item.snippet
                or "Поисковый результат без сниппета; требуется ручная проверка.",
                source_type=_source_type(item.source_class),
                evidence_level=item.evidence_level,
            )
        )
        known.add(item.id)

    counts: dict[str, int] = {}
    for source in external_sources:
        counts[source.source_class] = counts.get(source.source_class, 0) + 1
    if counts:
        analysis.risks_and_assumptions.append(
            "Внешний OSINT-контур: "
            + ", ".join(f"{kind}={count}" for kind, count in sorted(counts.items()))
            + ". Сниппеты требуют перехода к первоисточнику."
        )
    analysis.risks_and_assumptions.extend(search_notes)
    analysis.risks_and_assumptions.append(
        "Матрица 4×4 — техническая проекция бизнес-машины по КМ: I коммуникации, II люди, III технологии, IV менеджмент; измерения — внешний контур, внутренний контур, ресурсы/масштаб, результат/риски. Пустая ячейка означает отсутствие подтвержденных данных, а не отсутствие функции."
    )
    return analysis


async def run_company_intelligence(req: CompanyIntelligenceRequest) -> CompanyIntelligenceResult:
    """Collect external sources once and reuse them for the official-site deep analysis."""
    notes: list[str] = []
    official_url = str(req.url) if req.url else None
    sources, search_notes = await collect_external_sources(
        req.company_name,
        official_url,
        req.region,
        req.max_sources,
    )
    notes.extend(search_notes)

    if not official_url:
        official = next((source for source in sources if source.source_class == "official"), None)
        official_url = official.url if official else None

    site_analysis = None
    if official_url:
        try:
            site_analysis = await _analyze_site_with_sources(
                official_url,
                sources,
                search_notes,
            )
            official_url = site_analysis.url
        except (FetchError, httpx.HTTPError, ValueError) as exc:
            notes.append(f"Официальный сайт не удалось глубоко проанализировать: {exc}")

    counts = {
        kind: sum(1 for source in sources if source.source_class == kind)
        for kind in {source.source_class for source in sources}
    }
    scent_summary = [f"{kind}: {count}" for kind, count in sorted(counts.items())]
    if site_analysis:
        scent_summary.extend(signal.signal for signal in site_analysis.economic_signals[:5])

    score = (
        site_analysis.commercial_opportunity.score
        if site_analysis
        else min(60, 20 + len(sources) * 2)
    )
    solution = (
        site_analysis.commercial_opportunity.recommended_solution
        if site_analysis
        else "Требуется глубокий анализ официального сайта и перекрестная проверка источников."
    )
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
        status="complete" if site_analysis and sources else "partial",
    )
