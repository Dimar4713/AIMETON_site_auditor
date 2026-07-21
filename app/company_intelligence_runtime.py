from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.external_sources import (
    collect_external_sources,
    source_type,
    to_llm_sources,
    verified_evidence_level,
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


def _quote_from_document(text: str, limit: int = 500) -> str:
    normalized = " ".join(text.split())
    return normalized[:limit]


async def _analyze_site_with_sources(
    url: str,
    external_sources: list[IntelligenceSource],
    search_notes: list[str],
) -> SiteAnalysis:
    """Fetch the official document once and promote only that fetched document to evidence."""
    page = await fetch_site(url)
    document_accessed_at = datetime.now(timezone.utc).isoformat()
    quote = _quote_from_document(page["text"])

    official_candidate = next(
        (
            source
            for source in external_sources
            if source.url == url
            or source.url.rstrip("/") == page["final_url"].rstrip("/")
            or source.source_class == "official"
        ),
        None,
    )
    if official_candidate is not None:
        official_candidate.lifecycle_state = "evidence"
        official_candidate.document_url = page["final_url"]
        official_candidate.document_title = page["title"]
        official_candidate.document_accessed_at = document_accessed_at
        official_candidate.evidence_quote = quote
        official_candidate.evidence_level = verified_evidence_level("official")
        official_candidate.verification_note = "Первичный документ загружен и проверен."

    try:
        analysis = await analyze_with_routerai(
            page["final_url"],
            page["title"],
            page["text"],
            to_llm_sources(external_sources),
        )
    except Exception as exc:
        analysis = heuristic_analysis(page["final_url"], page["title"], page["text"])
        analysis.risks_and_assumptions.append(
            f"Использован резервный локальный анализ: {type(exc).__name__}."
        )

    if quote:
        evidence_id = official_candidate.id if official_candidate else "DOC1"
        known = {source.id for source in analysis.sources}
        if evidence_id not in known:
            analysis.sources.append(
                EvidenceSource(
                    id=evidence_id,
                    title=page["title"],
                    url=page["final_url"],
                    accessed_at=document_accessed_at,
                    evidence_quote=quote,
                    source_type="official_page",
                    evidence_level="confirmed_fact",
                    document_url=page["final_url"],
                    document_title=page["title"],
                    document_accessed_at=document_accessed_at,
                )
            )

    hint_count = sum(1 for source in external_sources if source.lifecycle_state == "discovery_hint")
    candidate_count = sum(1 for source in external_sources if source.lifecycle_state == "source_candidate")
    evidence_count = sum(1 for source in external_sources if source.lifecycle_state == "evidence")
    analysis.risks_and_assumptions.append(
        f"Контур источников: discovery_hint={hint_count}, source_candidate={candidate_count}, evidence={evidence_count}."
    )
    analysis.risks_and_assumptions.append(
        "Поисковые сниппеты не являются доказательствами; evidence создаётся только после загрузки документа с URL, датой и цитатой."
    )
    ambiguous = sum(1 for source in external_sources if source.classification_state == "ambiguous")
    unknown = sum(1 for source in external_sources if source.classification_state == "unknown")
    if ambiguous or unknown:
        analysis.risks_and_assumptions.append(
            f"Классификация источников требует проверки: ambiguous={ambiguous}, unknown={unknown}."
        )
    analysis.risks_and_assumptions.extend(search_notes)
    analysis.risks_and_assumptions.append(
        "Матрица 4×4 — техническая проекция бизнес-машины по КМ: I коммуникации, II люди, III технологии, IV менеджмент; измерения — внешний контур, внутренний контур, ресурсы/масштаб, результат/риски. Пустая ячейка означает отсутствие подтвержденных данных, а не отсутствие функции."
    )
    return analysis


async def run_company_intelligence(req: CompanyIntelligenceRequest) -> CompanyIntelligenceResult:
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
        official = next(
            (
                source
                for source in sources
                if source.source_class == "official"
                or (
                    source.result_kind == "official"
                    and source.classification_state != "ambiguous"
                )
            ),
            None,
        )
        if official:
            official.lifecycle_state = "source_candidate"
            official.verification_note = "Кандидат на официальный источник; ожидает загрузки документа."
            official_url = official.url

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
        state: sum(1 for source in sources if source.lifecycle_state == state)
        for state in ("discovery_hint", "source_candidate", "evidence")
    }
    scent_summary = [f"{state}: {count}" for state, count in counts.items()]
    if site_analysis:
        scent_summary.extend(signal.signal for signal in site_analysis.economic_signals[:5])

    verified_count = counts["evidence"]
    score = (
        site_analysis.commercial_opportunity.score
        if site_analysis
        else min(45, 15 + verified_count * 10)
    )
    solution = (
        site_analysis.commercial_opportunity.recommended_solution
        if site_analysis
        else "Требуется загрузка и проверка первичных документов; поисковые сниппеты являются только discovery hints."
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
        status="complete" if site_analysis and verified_count > 0 else "partial",
    )
