from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response


class NoCacheStaticFiles(StaticFiles):
    """Serve static assets with cache disabled so browsers always fetch the latest JS/CSS."""

    def file_response(self, *args, **kwargs) -> Response:
        resp = super().file_response(*args, **kwargs)
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp


from app.company_intelligence import run_company_intelligence, run_enriched_site_analysis
from app.discovery import run_hunt
from app.hunter_handbook import handbook
from app.hunter_sources import get_hunter_sources
from app.llm import chat_with_routerai
from app.mcp_server import mcp, mcp_http_app
from app.models import AnalyzeRequest, ChatRequest, CompanyIntelligenceRequest, HuntRequest
from app.osint_tools import get_osint_tools
from app.scraper import FetchError, fetch_site


app = FastAPI(
    title="AIMETON Site Auditor",
    version="0.5.1",
    lifespan=lambda _app: mcp.session_manager.run(),
)
app.mount("/static", NoCacheStaticFiles(directory="static"), name="static")
app.mount("/mcp", mcp_http_app, name="mcp")


@app.get("/")
def index():
    return FileResponse(
        Path("static/index.html"),
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "version": "0.5.1",
        "analysis_mode": "multi-source-osint-legal-ownership",
        "api": "/docs",
        "mcp": "/mcp",
    }


@app.get("/api/hunter-handbook")
def hunter_handbook():
    """Иерархический справочник отраслей, бизнес-моделей и экономических возможностей."""
    return handbook()


@app.get("/api/hunter-sources")
def hunter_sources():
    """Каталог источников обнаружения и подтверждения компаний."""
    return get_hunter_sources()


@app.get("/api/osint-tools")
def osint_tools():
    """Каталог OSINT-инструментов и уровней достоверности."""
    return get_osint_tools()


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    """Исследует сайт, внешние источники, судебный фон, владение и возможные связи."""
    try:
        page = await fetch_site(str(req.url))
        return await run_enriched_site_analysis(page["final_url"], page["title"], page["text"])
    except (FetchError, httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/company-intelligence")
async def company_intelligence(req: CompanyIntelligenceRequest):
    """Расширенный OSINT-профиль компании с юридическим и корпоративным контуром."""
    try:
        return await run_company_intelligence(req)
    except (FetchError, httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/hunt")
async def hunt(req: HuntRequest):
    """Автономная экономическая разведка по территории и параметрам охоты."""
    return await run_hunt(req)


@app.post("/api/chat")
async def chat(req: ChatRequest):
    reply = await chat_with_routerai(req.analysis, [m.model_dump() for m in req.messages])
    return {"reply": reply}
