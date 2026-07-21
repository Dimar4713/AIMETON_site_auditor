from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from app.company_intelligence import run_company_intelligence
from app.discovery import run_hunt
from app.heuristics import heuristic_analysis
from app.llm import analyze_with_routerai
from app.models import CompanyIntelligenceRequest, HuntRequest
from app.scraper import fetch_site


def _additional_allowlist_values(variable_name: str) -> list[str]:
    """Read a comma-separated operator allowlist without accepting wildcards."""
    values: list[str] = []
    for raw_value in os.getenv(variable_name, "").split(","):
        value = raw_value.strip()
        if value and "*" not in value:
            values.append(value)
    return values


_DEFAULT_ALLOWED_HOSTS = [
    "auditor.aimeton.ru",
    "auditor.aimeton.ru:443",
    "stage-auditor.aimeton.ru",
    "stage-auditor.aimeton.ru:443",
    "git-hub-site-auditor.replit.app",
    "git-hub-site-auditor.replit.app:443",
    "localhost",
    "localhost:8000",
    "127.0.0.1",
    "127.0.0.1:8000",
]

_DEFAULT_ALLOWED_ORIGINS = [
    "https://auditor.aimeton.ru",
    "https://stage-auditor.aimeton.ru",
    "https://git-hub-site-auditor.replit.app",
]

MCP_TRANSPORT_SECURITY = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=[
        *_DEFAULT_ALLOWED_HOSTS,
        *_additional_allowlist_values("AIMETON_MCP_ALLOWED_HOSTS"),
    ],
    allowed_origins=[
        *_DEFAULT_ALLOWED_ORIGINS,
        *_additional_allowlist_values("AIMETON_MCP_ALLOWED_ORIGINS"),
    ],
)

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
    transport_security=MCP_TRANSPORT_SECURITY,
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
