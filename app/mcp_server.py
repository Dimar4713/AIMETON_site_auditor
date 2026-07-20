from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from app.company_intelligence import run_company_intelligence
from app.discovery import run_hunt
from app.heuristics import heuristic_analysis
from app.llm import analyze_with_routerai
from app.models import CompanyIntelligenceRequest, HuntRequest
from app.scraper import fetch_site


mcp = FastMCP(
    "AIMETON Site Auditor",
    instructions=(
        "Экономическая разведка компаний: анализ официального сайта, поиск целей по отрасли "
        "и формирование проверяемого информационного запаха. Неподтвержденные упоминания "
        "не должны представляться как факты."
    ),
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
)


@mcp.tool()
async def analyze_site(url: str) -> dict:
    """Проанализировать конкретный публичный сайт и предложить коммерчески полезные AI-решения."""
    page = await fetch_site(url)
    try:
        result = await analyze_with_routerai(page["final_url"], page["title"], page["text"])
    except Exception:
        result = heuristic_analysis(page["final_url"], page["title"], page["text"])
        result.risks_and_assumptions.append(
            "Использован резервный локальный анализ; LLM была недоступна или вернула невалидный ответ."
        )
    return result.model_dump(mode="json")


@mcp.tool()
async def hunt_companies(
    region: str,
    industries: list[str] | None = None,
    focus: list[str] | None = None,
    search_zone: str | None = None,
    output_limit: int = 10,
) -> dict:
    """Найти и ранжировать компании по территории, отрасли и признакам коммерческой возможности."""
    request = HuntRequest(
        region=region,
        search_zone=search_zone,
        industries=industries or [],
        focus=focus or [],
        output_limit=output_limit,
    )
    result = await run_hunt(request)
    return result.model_dump(mode="json")


@mcp.tool()
async def company_intelligence(
    company_name: str,
    url: str | None = None,
    region: str | None = None,
    max_sources: int = 20,
) -> dict:
    """Собрать профиль компании: официальный сайт, новости, справочники, отзывы, вакансии и информационный запах."""
    request = CompanyIntelligenceRequest(
        company_name=company_name,
        url=url,
        region=region,
        max_sources=max_sources,
    )
    result = await run_company_intelligence(request)
    return result.model_dump(mode="json")


mcp_http_app = mcp.streamable_http_app()
