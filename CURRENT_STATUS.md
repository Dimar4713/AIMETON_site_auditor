# AIMETON Site Auditor · Current Status

_Last updated: 2026-07-21_

## Текущее положение

**Фаза:** SA-01 — стабилизация поискового и MCP-контура.

**Завершено:**

- `SA-01.1` / Issue #9 — baseline и минимальный CI;
- `SA-01.2` / Issue #10 — MCP stage host/origin и proxy-safe redirect.

**Текущая контрольная точка:** ожидание решения GO перед Issue #11.

**Следующая подготовленная задача:** `SA-01.3 — Устранить двойной внешний поиск` / Issue #11.

**Текущий main до merge SA-01.2:** `d6fda98257f8ebcf3635f4445ca0901ebc0d8b24`.

## Зафиксированный baseline

- приложение: `AIMETON Site Auditor 0.6.1`;
- Python CI: `3.11`;
- `pytest -q` проходит;
- импорт приложения проходит;
- `/api/health` и регистрация `/mcp` проверяются автоматически;
- разрешённые зависимости сохраняются как CI-артефакт.

## Результат SA-01.2

- точный путь `/mcp` перенаправляется относительным `307` на `/mcp/`;
- redirect не зависит от внутренней HTTP-схемы reverse proxy;
- разрешены явные production/stage Host и Origin;
- allowlist может расширяться через `AIMETON_MCP_ALLOWED_HOSTS` и `AIMETON_MCP_ALLOWED_ORIGINS`;
- wildcard-значения не принимаются;
- DNS-rebinding protection остаётся включённой;
- произвольные Host и Origin отклоняются;
- `/api/health` не затронут.

## Подготовленный Epic SA-01

- #9 — baseline и минимальный CI — завершено;
- #10 — MCP stage host/origin и redirect — завершено после merge текущего PR;
- #11 — устранение двойного внешнего поиска — следующий кандидат;
- #12 — классификация запросов и источников;
- #13 — discovery hint / source candidate / evidence;
- #14 — обязательный pre-score;
- #15 — регрессионный пакет KIMI;
- #16 — интеграционная проверка.

## Правило продолжения

Issue #11 не начинается автоматически. Перед новой runtime-веткой фиксируется отдельное решение GO.

Каждая рабочая ветка создаётся только от актуального `main`:

```text
одна Issue
→ одна ограниченная ветка
→ один проверяемый PR
→ зелёный CI
→ наблюдаемый результат
→ обновление CURRENT_STATUS.md
```

## Временный режим управления

До создания GitHub Project `AIMETON Development Control` оперативное состояние ведётся через:

- `CURRENT_STATUS.md`;
- Issues #7–#16;
- Pull Requests;
- tests / CI / validation evidence.
