from __future__ import annotations

import pytest

from app import company_intelligence_runtime as runtime
from app.heuristics import heuristic_analysis
from app.models import CompanyIntelligenceRequest, IntelligenceSource


@pytest.mark.asyncio
async def test_company_intelligence_collects_external_sources_once(monkeypatch):
    calls = 0
    sources = [
        IntelligenceSource(
            id="E1",
            title="Официальный сайт",
            url="https://example.com",
            snippet="Компания оказывает услуги.",
            accessed_at="2026-07-21T00:00:00+00:00",
            source_class="official",
            evidence_level="confirmed_fact",
        )
    ]

    async def fake_collect(company_name, official_url, region, max_sources):
        nonlocal calls
        calls += 1
        return sources, []

    async def fake_analyze(url, external_sources, search_notes):
        assert external_sources is sources
        assert search_notes == []
        return heuristic_analysis(
            url,
            "Example — официальный сайт",
            "Компания оказывает услуги клиентам и автоматизирует коммерческие процессы.",
        )

    monkeypatch.setattr(runtime, "collect_external_sources", fake_collect)
    monkeypatch.setattr(runtime, "_analyze_site_with_sources", fake_analyze)

    result = await runtime.run_company_intelligence(
        CompanyIntelligenceRequest(
            company_name="Example",
            url="https://example.com",
            max_sources=10,
        )
    )

    assert calls == 1
    assert result.official_url == "https://example.com"
    assert result.sources == sources
    assert result.site_analysis is not None


@pytest.mark.asyncio
async def test_company_intelligence_without_official_site_still_searches_once(monkeypatch):
    calls = 0

    async def fake_collect(company_name, official_url, region, max_sources):
        nonlocal calls
        calls += 1
        return [], ["нет результатов"]

    monkeypatch.setattr(runtime, "collect_external_sources", fake_collect)

    result = await runtime.run_company_intelligence(
        CompanyIntelligenceRequest(company_name="Unknown", max_sources=10)
    )

    assert calls == 1
    assert result.status == "partial"
    assert result.site_analysis is None
