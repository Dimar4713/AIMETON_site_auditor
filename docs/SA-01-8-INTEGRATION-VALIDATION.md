# SA-01.8 — Интеграционная проверка стабилизации

## Проверено локально и в CI

- полный pytest, включая KIMI regression pack;
- импорт FastAPI-приложения;
- `/api/health` возвращает status `ok` и версию `0.6.1`;
- `/mcp` возвращает относительный `307` на `/mcp/`;
- один внешний provider call в company-intelligence цикле;
- независимая классификация query/result/source;
- `discovery_hint` не является evidence;
- pre-score обязателен до deep processing;
- Hunter не запускает загрузку сайта ниже `deep_audit_score`.

## Сравнение с baseline SA-01.1

Baseline SA-01.1 подтверждал импорт, pytest, health и наличие MCP route. Текущий пакет сохраняет эти свойства и добавляет регрессионные гарантии SA-01.2–SA-01.7.

## Stage verification

Проверено 2026-07-22 на VPS stage `stage-auditor.aimeton.ru`, Docker-контур `Caddy → aimeton-auditor:5000`.

Подтверждено:

```text
GET /api/health → 200 OK, version 0.6.1
HEAD /mcp → 307 Temporary Redirect, Location: /mcp/
HEAD /mcp/ → 405 Method Not Allowed, Allow: GET, POST, DELETE
POST /mcp/ initialize → 200 OK, protocolVersion 2025-03-26
```

`405` на `HEAD /mcp/` допустим: MCP endpoint принимает `GET`, `POST`, `DELETE`. Критический прежний ответ `421 Misdirected Request` устранён.

Stage bundle обновлён с `3257eaa7270897da0190309894500ac029e6d298` до merge commit `38d1d08f5ef88edc3e63aca0cf05bbb4dcea743c`, контейнер пересобран и перезапущен; healthcheck прошёл.

## Решение

- локальная интеграция: PASS;
- CI: PASS;
- stage integration: PASS;
- SA-01.8 завершена;
- Issue #16 может быть закрыта как completed.

## Остаточные риски

1. Deployment bundle на VPS не обновлялся автоматически после merge; требуется отдельная задача автоматизации доставки `main → app-source → docker compose build/up`.
2. Реальные SearXNG/RouterAI ответы остаются внешними нестабильными зависимостями и проверяются контрактами, а не побитовым golden output.
3. Dynamic-rendering Chromium test ранее проявлял единичный timeout cleanup; повторные CI runs проходили.
