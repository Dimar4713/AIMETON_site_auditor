from __future__ import annotations

import json
import os
import re

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.llm import BASE_URL, MODEL


class HunterQueryPlan(BaseModel):
    normalized_region: str = Field(min_length=2, max_length=160)
    normalized_industries: list[str] = Field(default_factory=list, max_length=12)
    normalized_focus: list[str] = Field(default_factory=list, max_length=12)
    corrected_input_summary: str = Field(default="", max_length=500)
    query_variants: list[str] = Field(min_length=1, max_length=100)
    warnings: list[str] = Field(default_factory=list, max_length=12)


def _extract_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.S)
    return json.loads(cleaned)


def _dedupe_queries(values: list[str], limit: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = " ".join(str(value).split()).strip()
        key = normalized.casefold()
        if not normalized or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
        if len(result) >= limit:
            break
    return result


async def generate_hunter_query_plan(
    *,
    region: str,
    industries: list[str],
    focus: list[str],
    max_queries: int,
) -> HunterQueryPlan | None:
    """Normalize Hunter input and generate diverse search variants with bounded RouterAI use.

    Returns None on any provider/config/schema failure so the caller can safely fall back to
    the deterministic Hunter query builder.
    """
    key = os.getenv("ROUTERAI_API_KEY")
    if not key:
        return None

    max_queries = max(1, min(int(max_queries), 100))
    schema = HunterQueryPlan.model_json_schema()
    prompt = f"""Ты — Query Intelligence модуль AIMETON Hunter.

Задача: подготовить качественный план веб-поиска потенциальных компаний до обращения к поисковым провайдерам.

Правила:
1. Сохрани исходный смысл пользователя, территорию и отрасль.
2. Исправь только очевидные опечатки и орфографические ошибки. Не меняй смысл молча.
3. Нормализуй регион, отрасли и фокус.
4. Сгенерируй разнообразные поисковые варианты, которые реально расширяют покрытие, а не являются косметическими перефразированиями.
5. Используй уместные синонимы и отраслевые варианты только при высокой уверенности.
6. Часть запросов должна искать официальные сайты компаний; часть — локальные организации/сети/клиники/центры соответствующей отрасли; допускаются каталожные формулировки только как вспомогательный путь обнаружения.
7. Не выдумывай названия конкретных компаний, юридические лица, адреса или факты.
8. Не генерируй более {max_queries} query_variants.
9. Верни только JSON по схеме без Markdown.

Вход:
region={json.dumps(region, ensure_ascii=False)}
industries={json.dumps(industries, ensure_ascii=False)}
focus={json.dumps(focus, ensure_ascii=False)}

JSON schema:
{json.dumps(schema, ensure_ascii=False)}
"""
    payload = {
        "model": MODEL,
        "temperature": 0.1,
        "messages": [
            {
                "role": "system",
                "content": "Возвращай только валидный JSON. Не выдумывай компании и факты; твоя задача — исправление и расширение поисковых формулировок.",
            },
            {"role": "user", "content": prompt},
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.post(
                f"{BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json=payload,
            )
            response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        plan = HunterQueryPlan.model_validate(_extract_json(content))
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, ValidationError, json.JSONDecodeError):
        return None

    deduped = _dedupe_queries(plan.query_variants, max_queries)
    if not deduped:
        return None
    return plan.model_copy(update={"query_variants": deduped})
