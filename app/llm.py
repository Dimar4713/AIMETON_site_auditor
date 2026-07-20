from __future__ import annotations
import json, os, re
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


async def analyze_with_routerai(url: str, title: str, text: str) -> SiteAnalysis:
    key = os.getenv("ROUTERAI_API_KEY")
    if not key:
        raise RuntimeError("ROUTERAI_API_KEY не задан")
    schema = SiteAnalysis.model_json_schema()
    accessed_at = datetime.now(timezone.utc).isoformat()
    prompt = f"""Ты — аналитический модуль экономической разведки AIMETON Site Auditor.
Работай по принципу РПТК7 «Эссетер»: обнаружение экономических сигналов → квалификация и формирование коммерческого контура → подготовка и передача коммерческой возможности.

Проанализируй сайт компании только по данным ниже. Не выдумывай факты, выручку, число сотрудников, контакты и реальные потери. Все неподтверждённые выводы маркируй как гипотезы.

Нужно:
1. Кратко определить профиль компании.
2. Выделить экономические сигналы: где сложность выбора, ручная консультация, повторяющиеся вопросы, неструктурированная заявка или иной разрыв могут создавать потерю спроса, времени либо качества.
3. Сформировать одну главную коммерческую возможность и оценить её по шкале 0–100. Высокий балл допустим только при наличии прямых доказательств на странице.
4. Предложить 3–10 конкретных AI-инструментов, а не абстрактных «агентов».
5. Подготовить пакет действия: гипотеза о роли ЛПР, основание для контакта, демонстрационный сценарий, персональное первое сообщение и следующий шаг.
6. Не использовать агрессивные, манипулятивные или спамные методы. Первое сообщение должно быть деловым, коротким и опираться на наблюдаемую особенность сайта.
7. В risks_and_assumptions явно отделить доказательства от предположений.
8. Обязательно сформировать массив sources. Для текущего сайта используй источник S1 с URL {url}, заголовком {title!r}, временем проверки {accessed_at}. В evidence_quote приводи только короткую дословную цитату из TEXT, без пересказа и без выдумывания.
9. Каждый economic_signal должен содержать source_ids. Для сигналов, основанных на текущей странице, указывай ["S1"]. Если точной цитаты нет, снижай уверенность и прямо отмечай это как гипотезу.
10. Не приписывай источнику сведения, которых нет в TEXT. Не создавай внешние URL, которых тебе не дали.

Верни только JSON по схеме.
URL: {url}
TITLE: {title}
TEXT:
{text[:30000]}
JSON SCHEMA:
{json.dumps(schema, ensure_ascii=False)}"""
    payload = {
        "model": MODEL,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": "Возвращай валидный JSON без Markdown. Не подменяй доказательства предположениями. Для фактов указывай источник и точную цитату."},
            {"role": "user", "content": prompt},
        ],
    }
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(
            f"{BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json=payload,
        )
        response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    result = SiteAnalysis.model_validate(_extract_json(content))

    # Сервер гарантирует минимум один проверяемый источник даже при неполном ответе модели.
    if not result.sources:
        result.sources = [EvidenceSource(
            id="S1",
            title=title or url,
            url=url,
            accessed_at=accessed_at,
            evidence_quote=_fallback_quote(text),
            source_type="official_page",
        )]
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
