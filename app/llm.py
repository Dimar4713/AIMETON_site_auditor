from __future__ import annotations
import json, os, re
import httpx
from app.models import SiteAnalysis

BASE_URL = os.getenv("ROUTERAI_BASE_URL", "https://routerai.ru/api/v1")
MODEL = os.getenv("ROUTERAI_MODEL", "openai/gpt-4o-mini")

def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    return json.loads(text)

async def analyze_with_routerai(url: str, title: str, text: str) -> SiteAnalysis:
    key = os.getenv("ROUTERAI_API_KEY")
    if not key:
        raise RuntimeError("ROUTERAI_API_KEY не задан")
    schema = SiteAnalysis.model_json_schema()
    prompt = f"""Ты — AI-консультант агентства по разработке AI-агентов. Проанализируй сайт компании только по данным ниже. Не выдумывай факты. Предложи 5–10 конкретных AI-агентов именно для этого бизнеса. Верни только JSON по схеме.\nURL: {url}\nTITLE: {title}\nTEXT:\n{text[:30000]}\nJSON SCHEMA:\n{json.dumps(schema, ensure_ascii=False)}"""
    payload = {"model": MODEL, "temperature": 0.2, "messages": [{"role":"system","content":"Возвращай валидный JSON без Markdown."},{"role":"user","content":prompt}]}
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(f"{BASE_URL}/chat/completions", headers={"Authorization": f"Bearer {key}"}, json=payload)
        response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    return SiteAnalysis.model_validate(_extract_json(content))

async def chat_with_routerai(analysis: SiteAnalysis, messages: list[dict]) -> str:
    key = os.getenv("ROUTERAI_API_KEY")
    if not key:
        return "Для диалога необходимо настроить ROUTERAI_API_KEY."
    system = "Ты консультант по внедрению AI-агентов. Отвечай на основе проведённого анализа, отделяй факты от предположений, предлагай практичные следующие шаги. Анализ: " + analysis.model_dump_json()
    payload = {"model": MODEL, "temperature": 0.3, "messages": [{"role":"system","content":system}] + messages[-12:]}
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(f"{BASE_URL}/chat/completions", headers={"Authorization": f"Bearer {key}"}, json=payload)
        response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]
