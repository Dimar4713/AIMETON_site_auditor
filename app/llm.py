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
            {"role": "system", "content": "Возвращай валидный JSON без Markdown. Не подменяй доказательства предположениями."},
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
    return SiteAnalysis.model_validate(_extract_json(content))


async def chat_with_routerai(analysis: SiteAnalysis, messages: list[dict]) -> str:
    key = os.getenv("ROUTERAI_API_KEY")
    if not key:
        return "Для диалога необходимо настроить ROUTERAI_API_KEY."
    system = (
        "Ты консультант по развитию коммерческой возможности, выявленной AIMETON Site Auditor. "
        "Опирайся на доказательства анализа, явно называй гипотезы гипотезами, не обещай неподтверждённый эффект. "
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
