from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.discovery import run_hunt
from app.heuristics import heuristic_analysis
from app.hunter_handbook import handbook
from app.hunter_sources import get_hunter_sources
from app.llm import analyze_with_routerai, chat_with_routerai
from app.models import AnalyzeRequest, ChatRequest, HuntRequest
from app.scraper import FetchError, fetch_site

app = FastAPI(title="AIMETON Site Auditor", version="0.3.1")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index():
    return FileResponse(Path("static/index.html"))


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "0.3.1"}


@app.get("/api/hunter-handbook")
def hunter_handbook():
    """Иерархический справочник отраслей, бизнес-моделей и экономических возможностей."""
    return handbook()


@app.get("/api/hunter-sources")
def hunter_sources():
    """Каталог источников обнаружения и подтверждения компаний."""
    return get_hunter_sources()


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    try:
        page = await fetch_site(str(req.url))
        try:
            result = await analyze_with_routerai(page["final_url"], page["title"], page["text"])
        except Exception:
            result = heuristic_analysis(page["final_url"], page["title"], page["text"])
            result.risks_and_assumptions.append(
                "Использован резервный локальный анализ; LLM была недоступна или вернула невалидный ответ."
            )
        return result
    except (FetchError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/hunt")
async def hunt(req: HuntRequest):
    """Автономная экономическая разведка по территории и параметрам охоты."""
    return await run_hunt(req)


@app.post("/api/chat")
async def chat(req: ChatRequest):
    reply = await chat_with_routerai(req.analysis, [m.model_dump() for m in req.messages])
    return {"reply": reply}
