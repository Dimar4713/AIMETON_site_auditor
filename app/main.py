from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
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


from app.company_intelligence_runtime import run_company_intelligence
from app.discovery import run_hunt
from app.external_sources import run_enriched_site_analysis
from app.hunter_handbook import handbook
from app.hunter_sources import get_hunter_sources
from app.llm import chat_with_routerai
from app.mcp_server import mcp, mcp_http_app
from app.models import AnalyzeRequest, ChatRequest, CompanyIntelligenceRequest, HuntRequest
from app.osint_tools import get_osint_tools
from app.scraper import FetchError, fetch_site


app = FastAPI(
    title="AIMETON Site Auditor",
    version="0.6.1",
    lifespan=lambda _app: mcp.session_manager.run(),
)


@app.middleware("http")
async def canonical_mcp_path(request: Request, call_next):
    """Use a relative redirect so an HTTPS reverse proxy cannot produce an HTTP loop."""
    if request.url.path == "/mcp":
        return RedirectResponse(url="/mcp/", status_code=307)
    return await call_next(request)


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
        "version": "0.6.1",
        "analysis_mode": "ai-sales-with-canonical-km-company-profile",
        "osint": "contacts-finance-workforce-legal-ownership",
        "api": "/docs",
        "mcp": "/mcp",
    }


@app.get("/api/hunter-handbook")
def hunter_handbook():
    return handbook()


@app.get("/api/hunter-sources")
def hunter_sources():
    return get_hunter_sources()


@app.get("/api/osint-tools")
def osint_tools():
    return get_osint_tools()


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    """Finds an AI sales opportunity and enriches it with a source-traceable company and canonical KM profile."""
    try:
        page = await fetch_site(str(req.url))
        return await run_enriched_site_analysis(page["final_url"], page["title"], page["text"])
    except (FetchError, httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/company-intelligence")
async def company_intelligence(req: CompanyIntelligenceRequest):
    try:
        return await run_company_intelligence(req)
    except (FetchError, httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/hunt")
async def hunt(req: HuntRequest):
    return await run_hunt(req)


@app.post("/api/chat")
async def chat(req: ChatRequest):
    reply = await chat_with_routerai(req.analysis, [m.model_dump() for m in req.messages])
    return {"reply": reply}
