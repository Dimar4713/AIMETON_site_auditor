from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
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


from app.company_intelligence_runtime import run_company_intelligence
from app.discovery import run_hunt
from app.external_sources import run_enriched_site_analysis
from app.hunter_handbook import handbook
from app.hunter_sources import get_hunter_sources
from app.llm import chat_with_routerai
from app.mcp_security import McpSecurityMiddleware
from app.mcp_server import admin_mcp, admin_mcp_http_app, mcp, mcp_http_app
from app.models import AnalyzeRequest, ChatRequest, CompanyIntelligenceRequest, HuntRequest
from app.osint_tools import get_osint_tools
from app.runtime_core.api import router as runtime_router
from app.scraper import FetchError, fetch_site


@asynccontextmanager
async def lifespan(_app: FastAPI):
    async with mcp.session_manager.run(), admin_mcp.session_manager.run():
        yield


app = FastAPI(
    title="AIMETON Site Auditor",
    version="0.8.0",
    lifespan=lifespan,
)
app.include_router(runtime_router)


@app.middleware("http")
async def canonical_mcp_path(request: Request, call_next):
    """Return explicit relative Location headers independent of proxy scheme rewriting."""
    if request.url.path == "/mcp":
        return Response(status_code=307, headers={"Location": "/mcp/"})
    if request.url.path == "/mcp-admin":
        return Response(status_code=307, headers={"Location": "/mcp-admin/"})
    return await call_next(request)


app.mount("/static", NoCacheStaticFiles(directory="static"), name="static")
app.mount("/mcp", McpSecurityMiddleware(mcp_http_app, admin=False), name="mcp")
app.mount("/mcp-admin", McpSecurityMiddleware(admin_mcp_http_app, admin=True), name="mcp-admin")


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
        "version": app.version,
        "analysis_mode": "ai-sales-with-canonical-km-company-profile",
        "osint": "contacts-finance-workforce-legal-ownership",
        "api": "/docs",
        "mcp": "/mcp",
        "mcp_admin": "/mcp-admin",
        "mcp_security": "public-rate-limited-admin-authenticated",
        "runtime_core": "/api/runtime",
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
    """Find an AI sales opportunity and enrich it with a source-traceable company and canonical KM profile."""
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
