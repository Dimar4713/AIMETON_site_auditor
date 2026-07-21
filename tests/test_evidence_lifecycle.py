from __future__ import annotations

import pytest

from app import company_intelligence_runtime as runtime
from app.external_sources import to_llm_sources
from app.heuristics import heuristic_analysis
from app.models import IntelligenceSource


def hint() -> IntelligenceSource:
    return IntelligenceSource(
        id="H1",
        title="Поисковый результат",
        url="https://example.com/about",
        snippet="Компания сообщает о выручке 10 млрд рублей.",
        accessed_at="2026-07-22T00:00:00+00:00",
        source_class="official",
        query_kind="finance",
        result_kind="finance",
        classification_state="ambiguous",
    )


def test_search_snippet_is_not_evidence():
    source = hint()
    assert source.lifecycle_state == "discovery_hint"
    assert source.evidence_level == "unverified_mention"
    assert source.evidence_quote is None
    payload = to_llm_sources([source])[0]
    assert payload["lifecycle_state"] == "discovery_hint"
    assert payload["evidence_level"] == "unverified_mention"


@pytest.mark.asyncio
async def test_fetched_document_promotes_candidate_to_evidence(monkeypatch):
    source = hint()

    async def fake_fetch(url):
        return {
            "final_url": "https://example.com/about",
            "title": "Example — официальный сайт",
            "text": "Example производит оборудование. Подтвержденная информация первичного документа.",
        }

    async def fake_llm(url, title, text, sources):
        assert sources[0]["lifecycle_state"] == "evidence"
        assert sources[0]["evidence_level"] == "confirmed_fact"
        return heuristic_analysis(url, title, text)

    monkeypatch.setattr(runtime, "fetch_site", fake_fetch)
    monkeypatch.setattr(runtime, "analyze_with_routerai", fake_llm)

    analysis = await runtime._analyze_site_with_sources(
        "https://example.com/about",
        [source],
        [],
    )

    assert source.lifecycle_state == "evidence"
    assert source.document_url == "https://example.com/about"
    assert source.document_accessed_at
    assert source.evidence_quote
    assert source.evidence_level == "confirmed_fact"
    assert analysis.sources
    evidence = analysis.sources[-1]
    assert evidence.document_url == "https://example.com/about"
    assert evidence.evidence_quote


@pytest.mark.asyncio
async def test_failed_document_load_does_not_promote_hint(monkeypatch):
    source = hint()

    async def fake_fetch(url):
        raise ValueError("document unavailable")

    monkeypatch.setattr(runtime, "fetch_site", fake_fetch)

    with pytest.raises(ValueError):
        await runtime._analyze_site_with_sources(
            "https://example.com/about",
            [source],
            [],
        )

    assert source.lifecycle_state == "discovery_hint"
    assert source.evidence_level == "unverified_mention"
    assert source.evidence_quote is None


def test_evidence_source_requires_traceable_document_fields_when_created_by_runtime():
    source = hint()
    assert source.document_url is None
    assert source.document_accessed_at is None
    assert source.verification_note.startswith("Поисковый сниппет")
