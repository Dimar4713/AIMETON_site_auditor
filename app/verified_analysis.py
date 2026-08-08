from __future__ import annotations

from urllib.parse import urlparse

from app.external_sources import (
    collect_external_sources,
    extract_identity_anchors,
    source_type,
    to_llm_sources,
)
from app.external_verification import verify_external_sources
from app.heuristics import heuristic_analysis
from app.llm import analyze_with_routerai
from app.models import EvidenceSource, SiteAnalysis


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


async def run_verified_enriched_site_analysis(
    url: str,
    title: str,
    text: str,
) -> SiteAnalysis:
    """Analyze crawled first-party evidence plus verified external primary documents.

    Search results remain discovery hints until the document pipeline fetches the
    primary URL and confirms the resolved company identity in fetched content.
    """
    company_hint = title.split("—")[0].split("|")[0].strip() or _host(url)
    anchors = extract_identity_anchors(text, url)
    external_sources, notes, diagnostics = await collect_external_sources(
        company_hint,
        url,
        region=anchors.primary_region,
        max_sources=100,
        anchors=anchors,
    )
    verified = await verify_external_sources(
        external_sources,
        company_name=company_hint,
        anchors=anchors,
        max_documents=24,
    )

    try:
        analysis = await analyze_with_routerai(
            url,
            title,
            text,
            to_llm_sources(external_sources),
        )
    except Exception as exc:
        analysis = heuristic_analysis(url, title, text)
        analysis.readiness.provider_states["routerai"] = (
            "not_configured"
            if isinstance(exc, RuntimeError)
            and "ROUTERAI_API_KEY" in str(exc)
            else "failed"
        )
        analysis.risks_and_assumptions.append(
            f"Использован резервный локальный анализ: {type(exc).__name__}."
        )

    known_ids = {source.id for source in analysis.sources}
    for source in verified:
        if not source.evidence_quote or source.id in known_ids:
            continue
        analysis.sources.append(
            EvidenceSource(
                id=source.id,
                title=source.document_title or source.title,
                url=source.document_url or source.url,
                accessed_at=source.document_accessed_at or source.accessed_at,
                evidence_quote=source.evidence_quote,
                source_type=source_type(source.source_class),
                evidence_level=source.evidence_level,
                document_url=source.document_url,
                document_title=source.document_title,
                document_accessed_at=source.document_accessed_at,
                document_digest=source.document_digest,
                evidence_locator=source.evidence_locator,
                evidence_digest=source.evidence_digest,
                fetch_path=source.fetch_path,
            )
        )
        known_ids.add(source.id)

    discovery_count = sum(
        1 for source in external_sources if source.lifecycle_state == "discovery_hint"
    )
    candidate_count = sum(
        1 for source in external_sources if source.lifecycle_state == "source_candidate"
    )
    evidence_count = sum(
        1 for source in external_sources if source.lifecycle_state == "evidence"
    )
    anchor_parts = [
        f"domain={anchors.domain}" if anchors.domain else None,
        f"region={anchors.primary_region}" if anchors.primary_region else None,
        "inn=present" if anchors.inn else None,
        "ogrn=present" if anchors.ogrn else None,
        f"phones={len(anchors.phones)}" if anchors.phones else None,
    ]
    analysis.risks_and_assumptions.append(
        "Identity anchors для внешнего поиска: "
        + (", ".join(part for part in anchor_parts if part) or "не извлечены")
        + "."
    )
    analysis.risks_and_assumptions.append(
        "Контур внешних источников: "
        f"discovery_hint={discovery_count}, source_candidate={candidate_count}, "
        f"verified_evidence={evidence_count}."
    )
    analysis.risks_and_assumptions.append(
        "Поисковые сниппеты не считаются evidence; внешний источник включается в доказательную базу "
        "только после загрузки первичного документа и подтверждения identity."
    )
    analysis.risks_and_assumptions.append(
        f"Search gateway state={diagnostics.state}; attempts={len(diagnostics.attempts)}."
    )
    analysis.risks_and_assumptions.extend(notes)

    if evidence_count:
        analysis.readiness.evidence_quality = max(
            analysis.readiness.evidence_quality,
            min(1.0, 0.25 + 0.08 * evidence_count),
        )
    return analysis
