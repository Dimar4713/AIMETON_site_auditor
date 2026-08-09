from types import SimpleNamespace

import pytest

from app import discovery
from app.models import HuntRequest
from app.search_gateway.models import GatewayState, SearchDiagnostics, SearchItem, SearchResponse


def _request() -> HuntRequest:
    return HuntRequest(region="Красноярск", industries=["Стоматология"])


def test_supporting_sources_do_not_cross_deep_audit_threshold() -> None:
    req = _request()
    direct = discovery._pre_score(
        req,
        "Стоматология San-Dent в Красноярске: лечение и имплантация",
        "услуги, запись, протезирование",
        "https://san-dent-clinic.ru/",
    )
    directory = discovery._pre_score(
        req,
        "Лучшие стоматологии в Красноярске",
        "каталог клиник, адреса, цены, отзывы",
        "https://dentistfind.ru/krasnoyarsk",
    )
    article = discovery._pre_score(
        req,
        "Лучшие стоматологии в Красноярске 2026: рейтинг",
        "топ клиник с отзывами и адресами",
        "https://www.kp.ru/russia/krasnoyarsk/lechenie/luchshie-stomatologii/",
    )

    assert direct.score is not None and direct.score >= req.deep_audit_score
    assert directory.score is not None and directory.score <= 45
    assert article.score is not None and article.score <= 45
    assert any("источник" in reason for reason in directory.reasons)


def test_unrelated_catalog_noise_is_rejected_before_deep_audit() -> None:
    result = discovery._pre_score(
        _request(),
        "Каталог товаров интернет-магазина",
        "широкий ассортимент товаров",
        "https://www.ozon.ru/category",
    )
    assert result.score is not None
    assert result.score < _request().minimum_pre_score
    assert any("ни отрасли, ни региона" in reason for reason in result.reasons)


class _OneResultGateway:
    async def search(self, request, _policy):
        return SearchResponse(
            results=[
                SearchItem(
                    url="https://example-dent.ru/",
                    title="Стоматология Красноярск — услуги и запись",
                    snippet="лечение зубов имплантация услуги",
                    provider="fake",
                )
            ],
            diagnostics=SearchDiagnostics(state=GatewayState.SUCCESS, selected_provider="fake"),
        )


@pytest.mark.asyncio
async def test_deep_audit_without_region_confirmation_cannot_remain_priority(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AIMETON_RUNTIME_DB", str(tmp_path / "runtime.sqlite3"))
    monkeypatch.setattr(discovery, "get_search_gateway", lambda: _OneResultGateway())

    async def no_llm_plan(**_kwargs):
        return None

    async def fake_fetch(url: str):
        return {
            "final_url": url,
            "title": "Стоматология в Москве",
            "text": "Москва лечение зубов имплантация запись услуги " * 100,
        }

    monkeypatch.setattr(discovery, "generate_hunter_query_plan", no_llm_plan)
    monkeypatch.setattr(discovery, "_build_queries", lambda _req: ["стоматология Красноярск"])
    monkeypatch.setattr(discovery, "fetch_site", fake_fetch)
    monkeypatch.setattr(
        discovery,
        "heuristic_analysis",
        lambda url, title, text: SimpleNamespace(
            url=url,
            company_name=title,
            business_summary="test",
            commercial_opportunity=SimpleNamespace(
                score=100,
                qualification="Приоритетная",
                recommended_solution="test",
            ),
        ),
    )

    result = await discovery.run_hunt(
        HuntRequest(
            region="Красноярск",
            industries=["Стоматология"],
            max_queries=1,
            results_per_query=10,
            max_candidates=10,
            minimum_pre_score=35,
            deep_audit_score=60,
            output_limit=10,
            concurrency=1,
        )
    )

    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.deep_analysis_performed is True
    assert candidate.region_confirmed is False
    assert candidate.final_score == 49
    assert candidate.qualification == "Наблюдение"
