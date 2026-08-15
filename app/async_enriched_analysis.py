from __future__ import annotations

from app.external_sources import (
    _host,
    collect_external_sources,
    extract_identity_anchors,
    to_llm_sources,
)
from app.heuristics import heuristic_analysis
from app.models import SiteAnalysis
from app.routerai_context import compact_routerai_sources
from app.routerai_runtime import run_bounded_routerai_analysis


async def run_enriched_site_analysis(
    url: str,
    title: str,
    text: str,
) -> SiteAnalysis:
    """Async-analysis variant with bounded, observable LLM synthesis.

    Search and the authoritative source model remain unchanged. Only the LLM
    projection of discovery hints is compacted before RouterAI synthesis so a
    long OSINT tail does not dominate the model input budget.
    """
    company_hint = title.split("—")[0].split("|")[0].strip() or _host(url)
    anchors = extract_identity_anchors(text, url)
    external_sources, notes, _diagnostics = await collect_external_sources(
        company_hint,
        url,
        region=anchors.primary_region,
        max_sources=60,
        anchors=anchors,
    )
    llm_sources = compact_routerai_sources(to_llm_sources(external_sources))
    try:
        analysis = await run_bounded_routerai_analysis(
            url,
            title,
            text,
            llm_sources,
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

    anchor_parts = [
        f"domain={anchors.domain}" if anchors.domain else None,
        f"region={anchors.primary_region}" if anchors.primary_region else None,
        f"inn={anchors.inn}" if anchors.inn else None,
        f"ogrn={anchors.ogrn}" if anchors.ogrn else None,
    ]
    analysis.risks_and_assumptions.append(
        "Внешний поиск привязан к identity anchors: "
        + ", ".join(part for part in anchor_parts if part)
        + "."
    )
    analysis.risks_and_assumptions.append(
        f"Внешний поиск дал discovery_hint={len(external_sources)}; "
        "поисковые сниппеты не включены в evidence до проверки первичных документов."
    )
    analysis.risks_and_assumptions.extend(notes)
    return analysis
