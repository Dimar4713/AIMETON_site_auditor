from __future__ import annotations

import json
import os
import re
from enum import StrEnum

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.llm import BASE_URL, MODEL
from app.search_observer import SearchWaveTelemetry


class ObserverAction(StrEnum):
    BOOST = "boost"
    SLOW = "slow"
    STOP = "stop"
    REFINE = "refine"
    CONTINUE = "continue"
    ESCALATE = "escalate"


class ShadowObserverModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DirectionRecommendation(ShadowObserverModel):
    direction_index: int = Field(ge=0)
    action: ObserverAction
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1, max_length=300)
    refined_queries: list[str] = Field(default_factory=list, max_length=4)


class SearchObserverRecommendation(ShadowObserverModel):
    observer_mode: str = Field(default="shadow", pattern=r"^shadow$")
    routing_changed: bool = False
    sufficient_evidence: bool
    recommendations: list[DirectionRecommendation] = Field(default_factory=list, max_length=40)
    summary: str = Field(min_length=1, max_length=600)


def _extract_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.S)
    return json.loads(cleaned)


def _bounded_telemetry_payload(telemetry: SearchWaveTelemetry) -> dict:
    return {
        "query_count": telemetry.query_count,
        "result_count": telemetry.result_count,
        "unique_domain_count": telemetry.unique_domain_count,
        "duplicate_domain_ratio": telemetry.duplicate_domain_ratio,
        "provider_result_counts": telemetry.provider_result_counts,
        "attempt_states": telemetry.attempt_states,
        "latency_ms_total": telemetry.latency_ms_total,
        "degraded_attempts": telemetry.degraded_attempts,
        "total_cost_by_currency": {
            key: str(value) for key, value in telemetry.total_cost_by_currency.items()
        },
        "directions": [item.model_dump(mode="json") for item in telemetry.directions],
    }


async def evaluate_search_wave_shadow(
    telemetry: SearchWaveTelemetry,
) -> SearchObserverRecommendation | None:
    """Ask the LLM for advisory search-steering recommendations only.

    The returned object has no execution capability. Any future application of
    recommendations must pass a separate deterministic policy gate. Fail closed
    to None on missing config, transport failure or schema violation.
    """
    key = os.getenv("ROUTERAI_API_KEY")
    if not key:
        return None

    schema = SearchObserverRecommendation.model_json_schema()
    prompt = f"""Ты — Search Observer AIMETON Hunter. Работаешь строго в SHADOW MODE.

Твоя задача — оценить фактическую отдачу завершённой поисковой волны и предложить рекомендации для следующей волны. Ты НЕ управляешь поиском и не можешь менять runtime-политику.

Разрешённые рекомендации: boost, slow, stop, refine, continue, escalate.

Жёсткие правила:
1. Никогда не утверждай, что routing уже изменён. routing_changed всегда false.
2. Не предлагай обход CAPTCHA, блокировок, cooldown, circuit breaker, quota, budget или provider policy.
3. Не предлагай повышать concurrency или отключать safety limits.
4. Не выдумывай компании, результаты или факты, которых нет в telemetry.
5. Не помечай направление stop при слабом объёме наблюдений без высокой уверенности.
6. refine может содержать максимум 4 новых поисковых формулировки и не должен выдумывать конкретные компании.
7. escalate означает только рекомендацию запросить следующий разрешённый эшелон через policy gate; это не разрешение на платный вызов.
8. Верни только JSON по схеме.

Telemetry:
{json.dumps(_bounded_telemetry_payload(telemetry), ensure_ascii=False)}

JSON schema:
{json.dumps(schema, ensure_ascii=False)}
"""
    payload = {
        "model": MODEL,
        "temperature": 0.0,
        "messages": [
            {
                "role": "system",
                "content": "Ты advisory-only Search Observer. Верни только валидный JSON; routing_changed всегда false.",
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
        recommendation = SearchObserverRecommendation.model_validate(_extract_json(content))
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, ValidationError, json.JSONDecodeError):
        return None

    if recommendation.routing_changed:
        return None
    max_index = len(telemetry.directions) - 1
    if any(item.direction_index > max_index for item in recommendation.recommendations):
        return None
    return recommendation
