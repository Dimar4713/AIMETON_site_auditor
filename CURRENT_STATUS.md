# AIMETON Site Auditor · Current Status

_Last updated: 2026-07-22_

## Текущее положение

**Фаза:** SA-01 — завершена.

**Завершено:** SA-01.1–SA-01.8 / Issues #9–#16.

**Статус SA-01.8:** локальная интеграция, CI и внешний stage-контур подтверждены.

**Стабилизированный main:** `38d1d08f5ef88edc3e63aca0cf05bbb4dcea743c` плюс итоговые status/validation updates.

## Подтверждено

- полный pytest и KIMI regression pack;
- импорт приложения;
- `/api/health` на stage: `200 OK`, версия `0.6.1`;
- `/mcp`: `307 Temporary Redirect`, `Location: /mcp/`;
- `/mcp/`: больше не возвращает `421`; `HEAD` корректно отвечает `405` с `Allow: GET, POST, DELETE`;
- MCP initialize через `POST /mcp/`: `200 OK`, protocol `2025-03-26`;
- один provider call;
- независимая классификация;
- lifecycle `discovery_hint → source_candidate → evidence`;
- обязательный pre-score до deep processing;
- Hunter threshold pipeline.

## Stage deployment

Рабочий контур:

```text
stage-auditor.aimeton.ru
  → Caddy
  → Docker network aimeton-search
  → aimeton-auditor:5000
```

Stage bundle обновлён вручную с commit `3257eaa7270897da0190309894500ac029e6d298` до `38d1d08f5ef88edc3e63aca0cf05bbb4dcea743c`; образ пересобран, контейнер пересоздан и прошёл healthcheck.

## Следующий системный риск

Merge в GitHub пока не приводит к автоматическому обновлению deployment bundle `/opt/aimeton/auditor-stack/app-source` и перезапуску Docker-сервиса. Это отдельная инфраструктурная задача следующей фазы.

## Оперативное управление

Состояние синхронизируется через `CURRENT_STATUS.md`, GitHub Issues, Project-доску, Pull Requests и tests / CI / validation evidence.
