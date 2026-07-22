# AIMETON Site Auditor · Current Status

_Last updated: 2026-07-22_

## Текущее положение

**Фаза:** SA-02 — инфраструктурная устойчивость и автоматизация эксплуатации.

**Завершено:** SA-01.1–SA-01.8 / Issues #9–#16.

**Активно:** SA-02.1 / Issue #27 — автоматизировать deployment `main → VPS stage` через self-hosted GitHub Runner.

**Запланировано после SA-02.1:** SA-02.2 / Issue #28 — подключить внешний OpenStack-контур управления инфраструктурой immers.cloud.

**Стабилизированный application baseline:** `38d1d08f5ef88edc3e63aca0cf05bbb4dcea743c` плюс итоговые status/validation updates.

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

## План SA-02

### SA-02.1 — внутренний deployment-контур / Issue #27

Цель: после зелёного CI точный commit `main` автоматически, наблюдаемо и обратимо разворачивается на VPS через self-hosted Runner, Docker Compose, health/smoke checks и rollback.

Это текущий приоритет. OpenStack API для выполнения обычного deployment не требуется.

### SA-02.2 — внешний инфраструктурный контур / Issue #28

Цель: после стабилизации deployment подключить OpenStack Zed API immers.cloud как внешний уровень управления VM, сетью, дисками, snapshots и аварийным восстановлением.

Разделение ответственности:

```text
GitHub Runner → команды внутри Ubuntu → Docker deployment
OpenStack API → состояние и жизненный цикл VM → сеть, volumes, snapshots, recovery
```

SA-02.2 выполняется после SA-02.1. Основной пароль OpenStack не должен использоваться в автоматизации; требуется отдельный Application Credential с минимальными полномочиями. Destructive operations запрещены по умолчанию.

## Системные риски

1. Merge в GitHub пока не приводит к автоматическому обновлению deployment bundle `/opt/aimeton/auditor-stack/app-source` и перезапуску Docker-сервиса — закрывается SA-02.1 / #27.
2. Нет внешнего API-контура наблюдения и аварийного управления VM при недоступности Runner/SSH — запланировано SA-02.2 / #28.
3. OpenStack API не заменяет shell-доступ и не должен смешиваться с application deployment logic.

## Оперативное управление

Состояние синхронизируется через `CURRENT_STATUS.md`, GitHub Issues, Project-доску, Pull Requests и tests / CI / validation evidence.