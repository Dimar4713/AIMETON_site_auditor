from __future__ import annotations

from app.external_sources import (
    _host,
    collect_external_sources,
    extract_identity_anchors,
    to_llm_sources,
)
from app.heuristics import heuristic_analysis
from app.models import SiteAnalysis
from app.routerai_runtime import run_bounded_routerai_analysis


async def run_enriched_site_analysis(
    url: str,
    title: str,
    text: str,
) -> SiteAnalysis:
    """Async-analysis variant with a bounded, observable LLM synthesis step.

    The external search/evidence path remains identical to the established
    implementation. Only the final RouterAI synthesis is wrapped in its own
    deadline/span so an MCP mission does not consume the whole global mission
    budget waiting on one LLM call.
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
    try:
        analysis = await run_bounded_routerai_analysis(
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
