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

Целевые проверки:

```text
GET https://git-hub-site-auditor.replit.app/api/health
GET https://git-hub-site-auditor.replit.app/mcp        (ожидается 307 Location: /mcp/)
GET https://git-hub-site-auditor.replit.app/mcp/       (ожидается MCP endpoint без redirect loop)
```

Из текущей исполняющей среды stage-домен не разрешился по DNS. Web-safe-open также не смог открыть URL без индексируемого результата. Это внешний блокер наблюдения, а не подтверждённый дефект приложения.

## Решение

- локальная интеграция: PASS после зелёного CI;
- stage integration: BLOCKED — требуется фактический запрос из доступной сети;
- Issue #16 не закрывать до stage evidence;
- PR держать draft до подтверждения stage `/api/health` и `/mcp`.

## Остаточные риски

1. Stage может ещё работать на старом commit до завершения deployment.
2. Reverse proxy конкретного окружения может менять Host/Origin или redirect headers.
3. Dynamic-rendering Chromium test ранее проявлял единичный timeout cleanup; повторные CI runs проходили.
4. Реальные SearXNG/RouterAI ответы остаются внешними нестабильными зависимостями и проверяются контрактами, а не побитовым golden output.
