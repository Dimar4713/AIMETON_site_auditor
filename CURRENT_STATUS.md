# AIMETON Site Auditor · Current Status

_Last updated: 2026-07-22_

## Текущее положение

**Завершённая фаза:** SA-01 — стабилизация поискового и MCP-контура.

**Завершено:** SA-01.1–SA-01.8 / Issues #9–#16; Epic #7 закрыт.

**Активная фаза:** SA-02 — замыкание эксплуатационного контура.

**Текущий шаг:** SA-02.1 / Issue #27 — автоматизация deployment `main → VPS stage`.

**Следующий отложенный шаг:** SA-02.2 / Issue #28 — OpenStack-контур управления инфраструктурой immers.cloud после завершения SA-02.1.

## Подтверждённый baseline stage

- `/api/health` на stage: `200 OK`, версия `0.6.1`;
- `/mcp`: `307 Temporary Redirect`, `Location: /mcp/`;
- `/mcp/`: `HEAD 405`, `Allow: GET, POST, DELETE`, без `421`;
- MCP initialize: `200 OK`, protocol `2025-03-26`;
- стабилизированный bundle вручную обновлён до commit `38d1d08f5ef88edc3e63aca0cf05bbb4dcea743c`.

## SA-02.1 — текущее состояние реализации

Подготовлен автоматизированный контур:

```text
Baseline CI success on main
  → Deploy Stage workflow
  → self-hosted runner /home/ubuntu/actions-runner
  → exact commit checkout
  → transactional app-source switch
  → docker compose build/up
  → health + MCP smoke
  → rollback on failure
  → deployment evidence artifact
```

В реализации предусмотрены:

- полный целевой commit SHA;
- блокировка параллельных deployment через `flock`;
- временный валидируемый bundle;
- атомарное переключение `app-source`;
- резервная копия предыдущего bundle;
- Docker health wait;
- внешние smoke-проверки health, redirect и MCP initialize;
- автоматический rollback;
- фиксация SHA, состояния контейнера и HTTP evidence;
- ручная инструкция восстановления.

SA-02.1 нельзя закрывать до фактического успешного workflow run на `main` и отдельного контролируемого rollback test.

## Разделение контуров управления

### Внутренний эксплуатационный контур — SA-02.1

```text
GitHub Actions
  → self-hosted Runner внутри Ubuntu
  → Docker Compose
  → приложение
```

### Внешний инфраструктурный контур — SA-02.2

```text
AIMETON control
  → OpenStack API immers.cloud
  → VM, network, volumes, snapshots, recovery
```

OpenStack API не заменяет выполнение команд внутри Ubuntu.

## Оперативное управление

Состояние синхронизируется через `CURRENT_STATUS.md`, GitHub Issues, Pull Requests, Actions runs, deployment evidence и stage smoke results.
