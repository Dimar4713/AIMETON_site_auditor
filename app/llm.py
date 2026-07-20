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


async def analyze_with_routerai(url: str, title: str, text: str, external_sources: list[dict] | None = None) -> SiteAnalysis:
    key = os.getenv("ROUTERAI_API_KEY")
    if not key:
        raise RuntimeError("ROUTERAI_API_KEY не задан")

    schema = SiteAnalysis.model_json_schema()
    accessed_at = datetime.now(timezone.utc).isoformat()
    external_sources = external_sources or []
    external_context = json.dumps(external_sources, ensure_ascii=False, indent=2)[:52000]

    prompt = f"""Ты — аналитический модуль экономической разведки AIMETON Site Auditor.
Твоя задача — восстановить проверяемую модель бизнес-машины компании, а не только описать сайт.

ДОКАЗАТЕЛЬНОСТЬ
1. S1 — официальный сайт. Внешние источники имеют id E1, E2 и т.д. Используй только эти id.
2. Не создавай URL, цифры, людей, контакты и факты, отсутствующие во входных данных.
3. Поисковый сниппет — сигнал. Высокая уверенность допустима для официального источника, государственного реестра или двух независимых согласующихся источников.
4. Для каждого факта, сигнала и ячейки матрицы указывай source_ids.
5. Не найдено — пиши «Нет данных», а не делай вывод об отсутствии.
6. Финансовые показатели всегда сопровождай периодом. Не смешивай выручку, прибыль, активы, налоги и оборот.
7. Зарегистрированный учредитель не автоматически является фактическим владельцем. Аффилированность и бенефициарность маркируй как гипотезу до подтверждения.
8. Наличие судебного дела не означает виновность. Указывай роль компании, если она видна: истец, ответчик, третье лицо.

ОБЯЗАТЕЛЬНЫЙ ПРОФИЛЬ COMPANY_FACTS
Извлеки, когда подтверждено: юридическое и брендовое название, ИНН, ОГРН, статус, адреса, телефоны, email, сайт, соцсети, численность персонала, выручку, прибыль, активы, налоги, учредителей, руководителей, предполагаемых бенефициаров, аффилированные компании, географию, продукты, клиентов и поставщиков. Для неизвестного поля не выдумывай запись.

МАТРИЦА БИЗНЕС-МАШИНЫ 4×4 ПО КМ
Сформируй ровно 16 ячеек business_machine_4x4 — по четыре измерения для каждого двигателя:
I — Коммуникационные системы:
 I-EXT внешний контур: маркетинг, каналы, сайт, соцсети, продажи, партнёры, контакты;
 I-INT внутренний контур: CRM, обработка лидов, коммуникации подразделений, документооборот;
 I-SCALE ресурсы и масштаб: клиентская база, география, каналы, охват, репутация;
 I-RISK результат и риски: конверсия, потеря спроса, отзывы, зависимость от ручных контактов.
II — Люди:
 II-EXT внешний контур: клиенты, партнёры, подрядчики, сообщество, рынок труда;
 II-INT внутренний контур: численность, роли, компетенции, вакансии, культура;
 II-SCALE ресурсы и масштаб: команда, эксперты, производительность, кадровый резерв;
 II-RISK результат и риски: текучесть, дефицит компетенций, перегрузка, зависимость от ключевых лиц.
III — Технологии:
 III-EXT внешний контур: продукт, оборудование, клиентские цифровые сервисы, интеграции;
 III-INT внутренний контур: ИТ-системы, автоматизация, данные, производство, контроль качества;
 III-SCALE ресурсы и масштаб: мощности, активы, патенты, лицензии, инфраструктура;
 III-RISK результат и риски: устаревание, ручные операции, сбои, кибер- и технологические риски.
IV — Менеджмент:
 IV-EXT внешний контур: стратегия, юридическая структура, собственники, регуляторы, тендеры;
 IV-INT внутренний контур: управление, процессы, KPI, финансы, планирование;
 IV-SCALE ресурсы и масштаб: выручка, прибыль, активы, филиалы, контракты, инвестиции;
 IV-RISK результат и риски: суды, долги, исполнительные производства, банкротство, концентрация власти.

Для каждой ячейки: finding, status, confidence, source_ids, gap_or_opportunity. Даже при отсутствии данных создай ячейку со status="Нет данных".

КОММЕРЧЕСКИЙ ВЫВОД
После реконструкции 4×4 выбери не самую красивую, а наиболее доказанную и экономически значимую возможность. Оценка 80+ допустима только при прямом подтверждении проблемы, масштаба и реалистичного пилота. Предложи 3–10 конкретных AI-инструментов и пакет действия.

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
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": "Возвращай валидный JSON без Markdown. Не подменяй отсутствие данных предположениями."},
            {"role": "user", "content": prompt},
        ],
    }
    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(
            f"{BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json=payload,
        )
        response.raise_for_status()
    result = SiteAnalysis.model_validate(_extract_json(response.json()["choices"][0]["message"]["content"]))

    if not any(source.id == "S1" for source in result.sources):
        result.sources.insert(0, EvidenceSource(
            id="S1", title=title or url, url=url, accessed_at=accessed_at,
            evidence_quote=_fallback_quote(text), source_type="official_page", evidence_level="confirmed_fact",
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
            evidence_quote=str(item.get("snippet") or source.evidence_quote)[:900],
            source_type=str(item.get("source_type") or "external_source"),
            evidence_level=str(item.get("evidence_level") or "unverified_mention"),
        ))
        seen_ids.add(source.id)
    result.sources = clean_sources

    known_ids = {source.id for source in result.sources}
    for signal in result.economic_signals:
        signal.source_ids = [source_id for source_id in signal.source_ids if source_id in known_ids]
    for fact in result.company_facts:
        fact.source_ids = [source_id for source_id in fact.source_ids if source_id in known_ids]
    for cell in result.business_machine_4x4:
        cell.source_ids = [source_id for source_id in cell.source_ids if source_id in known_ids]
    return result


async def chat_with_routerai(analysis: SiteAnalysis, messages: list[dict]) -> str:
    key = os.getenv("ROUTERAI_API_KEY")
    if not key:
        return "Для диалога необходимо настроить ROUTERAI_API_KEY."
    system = (
        "Ты консультант AIMETON по бизнес-машине 4×4 КМ. Опирайся на company_facts, business_machine_4x4 и sources. "
        "Явно разделяй факты, выводы и гипотезы; не обещай неподтверждённый эффект. Анализ: "
        + analysis.model_dump_json()
    )
    payload = {
        "model": MODEL,
        "temperature": 0.25,
        "messages": [{"role": "system", "content": system}] + messages[-12:],
    }
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            f"{BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json=payload,
        )
        response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]
