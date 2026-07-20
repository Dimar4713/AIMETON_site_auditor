from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone

import httpx

from app.models import EvidenceSource, SiteAnalysis


BASE_URL = os.getenv("ROUTERAI_BASE_URL", "https://routerai.ru/api/v1")
MODEL = os.getenv("ROUTERAI_MODEL", "openai/gpt-4o-mini")


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    return json.loads(text)


def _fallback_quote(text: str, limit: int = 320) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact[:limit] if compact else "Текст страницы не извлечён."


async def analyze_with_routerai(
    url: str,
    title: str,
    text: str,
    external_sources: list[dict] | None = None,
) -> SiteAnalysis:
    key = os.getenv("ROUTERAI_API_KEY")
    if not key:
        raise RuntimeError("ROUTERAI_API_KEY не задан")

    schema = SiteAnalysis.model_json_schema()
    accessed_at = datetime.now(timezone.utc).isoformat()
    external_sources = external_sources or []
    external_context = json.dumps(external_sources, ensure_ascii=False, indent=2)[:24000]

    prompt = f"""Ты — аналитический модуль экономической разведки AIMETON Site Auditor.
Работай по принципу РПТК7 «Эссетер»: обнаружение экономических сигналов → перекрёстная проверка → квалификация → пакет действия.

Проанализируй официальный сайт и переданные внешние OSINT-источники. Не выдумывай факты, выручку, сотрудников, контакты, патенты, тендеры и реальные потери. Все неподтверждённые выводы маркируй как гипотезы.

Правила доказательности:
1. S1 — официальный сайт. Для фактов с сайта используй source_ids=["S1"].
2. Внешние источники уже имеют идентификаторы E1, E2... Используй только эти идентификаторы.
3. Не создавай URL или источники, отсутствующие во входных данных.
4. Поисковый сниппет — это сигнал, а не автоматически подтверждённый факт.
5. Факт высокой уверенности требует официального источника либо двух независимых согласующихся источников.
6. Отзывы, соцсети и вакансии трактуй как слабые или косвенные сигналы.
7. Противоречия между источниками явно укажи в risks_and_assumptions.
8. Оценка 80+ допустима только при прямом подтверждении проблемы и наличии реалистичного демонстрационного сценария.

Нужно:
1. Определить профиль компании и цифровой контур.
2. Выделить экономические сигналы сайта и внешней среды.
3. Сформировать одну главную коммерческую возможность и оценить 0–100.
4. Предложить 3–10 конкретных AI-инструментов.
5. Подготовить пакет действия: гипотеза роли ЛПР, основание, демонстрация, первое сообщение, следующий шаг.
6. В sources включить S1 и только использованные внешние источники с их исходными id, URL, цитатой/сниппетом, датой, типом и уровнем доказательности.
7. В economic_signals обязательно заполнять source_ids.
8. Не использовать агрессивные, манипулятивные или спамные методы.

Верни только JSON по схеме.

OFFICIAL URL: {url}
TITLE: {title}
ACCESSED AT: {accessed_at}
OFFICIAL PAGE TEXT:
{text[:30000]}

EXTERNAL OSINT SOURCES:
{external_context}

JSON SCHEMA:
{json.dumps(schema, ensure_ascii=False)}"""

    payload = {
        "model": MODEL,
        "temperature": 0.15,
        "messages": [
            {
                "role": "system",
                "content": "Возвращай валидный JSON без Markdown. Не подменяй доказательства предположениями и не создавай источники.",
            },
            {"role": "user", "content": prompt},
        ],
    }
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            f"{BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json=payload,
        )
        response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    result = SiteAnalysis.model_validate(_extract_json(content))

    if not any(source.id == "S1" for source in result.sources):
        result.sources.insert(0, EvidenceSource(
            id="S1",
            title=title or url,
            url=url,
            accessed_at=accessed_at,
            evidence_quote=_fallback_quote(text),
            source_type="official_page",
            evidence_level="confirmed_fact",
        ))

    allowed_external = {str(item.get("id")): item for item in external_sources}
    clean_sources: list[EvidenceSource] = []
    seen_ids: set[str] = set()
    for source in result.sources:
        if source.id in seen_ids:
            continue
        if source.id == "S1":
            clean_sources.append(source)
            seen_ids.add(source.id)
            continue
        item = allowed_external.get(source.id)
        if not item:
            continue
        clean_sources.append(EvidenceSource(
            id=source.id,
            title=str(item.get("title") or source.title),
            url=str(item.get("url") or source.url),
            accessed_at=str(item.get("accessed_at") or accessed_at),
            evidence_quote=str(item.get("snippet") or source.evidence_quote)[:700],
            source_type=str(item.get("source_type") or "external_source"),
            evidence_level=str(item.get("evidence_level") or "unverified_mention"),
        ))
        seen_ids.add(source.id)
    result.sources = clean_sources

    known_ids = {source.id for source in result.sources}
    for signal in result.economic_signals:
        signal.source_ids = [source_id for source_id in signal.source_ids if source_id in known_ids]
        if not signal.source_ids and "S1" in known_ids:
            signal.source_ids = ["S1"]
    return result


async def chat_with_routerai(analysis: SiteAnalysis, messages: list[dict]) -> str:
    key = os.getenv("ROUTERAI_API_KEY")
    if not key:
        return "Для диалога необходимо настроить ROUTERAI_API_KEY."
    system = (
        "Ты консультант по развитию коммерческой возможности, выявленной AIMETON Site Auditor. "
        "Опирайся на доказательства анализа и ссылки из sources, явно называй гипотезы гипотезами, не обещай неподтверждённый эффект. "
        "Помогай уточнить ценность, демонстрационный сценарий, корректный первый контакт и следующий проверяемый шаг. "
        "Не предлагай массовый спам или скрытую автоматизацию контактов. Анализ: "
        + analysis.model_dump_json()
    )
    payload = {
        "model": MODEL,
        "temperature": 0.3,
        "messages": [{"role": "system", "content": system}] + messages[-12:],
    }
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(
            f"{BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json=payload,
        )
        response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]
