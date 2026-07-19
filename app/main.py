from pathlib import Path
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.models import AnalyzeRequest, ChatRequest
from app.scraper import fetch_site, FetchError
from app.llm import analyze_with_routerai, chat_with_routerai
from app.heuristics import heuristic_analysis

app = FastAPI(title="AIMETON Site Auditor", version="0.1.0")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def index():
    return FileResponse(Path("static/index.html"))

@app.get("/api/health")
def health():
    return {"status": "ok"}

@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    try:
        page = await fetch_site(str(req.url))
        try:
            result = await analyze_with_routerai(page["final_url"], page["title"], page["text"])
        except Exception:
            result = heuristic_analysis(page["final_url"], page["title"], page["text"])
            result.risks_and_assumptions.append("Использован резервный локальный анализ; LLM была недоступна или вернула невалидный ответ.")
        return result
    except (FetchError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@app.post("/api/chat")
async def chat(req: ChatRequest):
    reply = await chat_with_routerai(req.analysis, [m.model_dump() for m in req.messages])
    return {"reply": reply}
