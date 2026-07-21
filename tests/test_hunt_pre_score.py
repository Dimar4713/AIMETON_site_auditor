from __future__ import annotations

import pytest

from app import discovery
from app.models import HuntRequest


def _request(**overrides) -> HuntRequest:
    data = {
        "region": "Красноярск",
        "industries": ["стоматология"],
        "focus": ["автоматизация"],
        "minimum_pre_score": 35,
        "deep_audit_score": 60,
        "max_queries": 1,
        "results_per_query": 10,
    }
    data.update(overrides)
    return HuntRequest(**data)


def test_pre_score_is_explainable_and_independent_of_link_count():
    req = _request()
    first = discovery._pre_score(
        req,
        "Стоматология Красноярск — каталог услуг",
        "Проектирование, подбор и автоматизация записи",
        "https://clinic.ru/services",
    )
    second = discovery._pre_score(
        req,
        "Стоматология Красноярск — каталог услуг",
        "Проектирование, подбор и автоматизация записи",
        "https://clinic.ru/services?many=links",
    )

    assert first.status == "calculated"
    assert first.score == second.score
    assert first.factors["region_match"] == 25
    assert first.factors["commercial_choice"] == 20
    assert first.factors["focus_match"] == 10


def test_missing_text_is_explicit_insufficient_data_not_zero():
    result = discovery._pre_score(_request(), "", "", "https://example.ru")

    assert result.status == "insufficient_data"
    assert result.score is None
    assert result.factors["region_match"] is None


@pytest.mark.asyncio
async def test_deep_processing_is_not_called_below_threshold(monkeypatch):
    req = _request(deep_audit_score=90)
    monkeypatch.setattr(
        discovery,
        "_build_queries",
        lambda _req: ["query"],
    )

    async def fake_search(_query: str, _limit: int):
        return [{
            "url": "https://clinic.ru",
            "title": "Стоматология Красноярск",
            "content": "Каталог услуг и подбор лечения",
        }]

    async def forbidden_fetch(_url: str):
        raise AssertionError("fetch_site must not run below deep_audit_score")

    monkeypatch.setattr(discovery, "_search_searxng", fake_search)
    monkeypatch.setattr(discovery, "fetch_site", forbidden_fetch)

    result = await discovery.run_hunt(req)

    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.pre_score_status == "calculated"
    assert candidate.deep_analysis_performed is False
    assert candidate.analysis is None


@pytest.mark.asyncio
async def test_deep_processing_runs_only_after_threshold(monkeypatch):
    req = _request(deep_audit_score=50)
    monkeypatch.setattr(discovery, "_build_queries", lambda _req: ["query"])

    async def fake_search(_query: str, _limit: int):
        return [{
            "url": "https://clinic.ru",
            "title": "Стоматология Красноярск — каталог услуг",
            "content": "Производство, проект и автоматизация записи",
        }]

    calls = {"fetch": 0}

    async def fake_fetch(url: str):
        calls["fetch"] += 1
        return {
            "final_url": url,
            "title": "Клиника Красноярск",
            "text": "Красноярск стоматология услуги запись автоматизация " * 30,
        }

    monkeypatch.setattr(discovery, "_search_searxng", fake_search)
    monkeypatch.setattr(discovery, "fetch_site", fake_fetch)

    result = await discovery.run_hunt(req)

    assert calls["fetch"] == 1
    assert result.candidates[0].deep_analysis_performed is True
    assert result.candidates[0].analysis is not None


@pytest.mark.asyncio
async def test_insufficient_candidate_never_starts_deep_processing(monkeypatch):
    req = _request(minimum_pre_score=0, deep_audit_score=0)
    monkeypatch.setattr(discovery, "_build_queries", lambda _req: ["query"])

    async def fake_search(_query: str, _limit: int):
        return [{"url": "https://example.ru", "title": "", "content": ""}]

    async def forbidden_fetch(_url: str):
        raise AssertionError("insufficient_data candidate must not be fetched")

    monkeypatch.setattr(discovery, "_search_searxng", fake_search)
    monkeypatch.setattr(discovery, "fetch_site", forbidden_fetch)

    result = await discovery.run_hunt(req)

    assert result.candidates[0].pre_score_status == "insufficient_data"
    assert result.candidates[0].preliminary_score is None
