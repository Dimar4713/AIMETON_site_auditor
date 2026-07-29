from contextlib import asynccontextmanager
import os
from pathlib import Path
import re

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
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
from app.search_gateway import get_search_gateway
from app.sef.company_profile import (
    CompanyProfileBuildRequest,
    CompanyProfileV1,
    build_company_profile_from_request,
)
from app.sef.report import (
    HumanReviewedReportV1,
    ReportBuildRequest,
    ReportReleaseError,
    ReportReviewPackage,
    ReportReviewPackageRequest,
    build_human_reviewed_report,
    build_review_package_from_request,
    render_report_html,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    async with mcp.session_manager.run(), admin_mcp.session_manager.run():
        yield


app = FastAPI(
    title="AIMETON Site Auditor",
    version="0.10.0",
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


def deployment_sha() -> str | None:
    value = os.getenv("AIMETON_DEPLOY_SHA", "").strip()
    if not value:
        path = Path(".aimeton-deploy-sha")
        if path.is_file():
            value = path.read_text(encoding="utf-8").strip()
    return value if re.fullmatch(r"[0-9a-f]{40}", value) else None


@app.get("/api/health")
def health():
    identity = deployment_sha()
    payload = {
        "status": "ok",
        "version": app.version,
        "analysis_mode": "ai-sales-with-canonical-km-company-profile",
        "osint": "contacts-finance-workforce-legal-ownership",
        "api": "/docs",
        "mcp": "/mcp",
        "mcp_admin": "/mcp-admin",
        "mcp_security": "public-rate-limited-admin-authenticated",
        "runtime_core": "/api/runtime",
        "search_gateway": "/api/search/health",
        "sef_company_profile": "/api/sef/company-profile",
        "sef_report_review_package": "/api/sef/report/review-package",
        "sef_report": "/api/sef/report",
    }
    if identity:
        payload["deployment_sha"] = identity
    return payload


@app.get("/api/search/health")
def search_health():
    providers = [
        item.model_dump(mode="json")
        for item in get_search_gateway().health()
    ]
    configured = [item for item in providers if item["configured"]]
    return {
        "status": "ok" if configured else "degraded",
        "providers": providers,
        "secrets_exposed": False,
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


@app.post(
    "/api/sef/company-profile",
    response_model=CompanyProfileV1,
)
def sef_company_profile(req: CompanyProfileBuildRequest):
    try:
        return build_company_profile_from_request(req)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post(
    "/api/sef/report/review-package",
    response_model=ReportReviewPackage,
)
def sef_report_review_package(req: ReportReviewPackageRequest):
    try:
        return build_review_package_from_request(req)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _build_report_or_http_error(
    req: ReportBuildRequest,
) -> HumanReviewedReportV1:
    try:
        return build_human_reviewed_report(req)
    except ReportReleaseError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "report_release_blocked",
                "blockers": exc.blockers,
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post(
    "/api/sef/report",
    response_model=HumanReviewedReportV1,
)
def sef_report(req: ReportBuildRequest):
    return _build_report_or_http_error(req)


@app.post(
    "/api/sef/report.html",
    response_class=HTMLResponse,
)
def sef_report_html(req: ReportBuildRequest):
    return HTMLResponse(render_report_html(_build_report_or_http_error(req)))


@app.post("/api/hunt")
async def hunt(req: HuntRequest):
    return await run_hunt(req)


@app.post("/api/chat")
async def chat(req: ChatRequest):
    reply = await chat_with_routerai(req.analysis, [m.model_dump() for m in req.messages])
    return {"reply": reply}
