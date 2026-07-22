# AIMETON Site Auditor · Current Status

_Last updated: 2026-07-22_

## Текущее положение

**Завершённая фаза:** SA-01 — стабилизация поискового и MCP-контура.

**Завершено:** SA-01.1–SA-01.8 / Issues #9–#16; Epic #7 закрыт.

**Завершённый эксплуатационный шаг:** SA-02.1 / Issue #27 — автоматизация deployment `main → VPS stage`.

**Активный следующий шаг:** SA-02.2 / Issue #28 — OpenStack-контур управления инфраструктурой immers.cloud.

## Подтверждённый stage

- `/api/health`: `200 OK`, версия `0.6.1`;
- `/mcp`: `307 Temporary Redirect`, `Location: /mcp/`;
- `/mcp/`: без `421`, MCP initialize отвечает `200 OK`;
- первый автоматический deployment выполнен для merge SHA `cf55c5c808a92524a1e85846b13b07b202dfe8af`;
- self-hosted runner `aimeton-site-auditor-stage` зарегистрирован в `Dimar4713/AIMETON_site_auditor` и работает как systemd service;
- GitHub Actions `Deploy Stage` завершён успешно.

## SA-02.1 — завершено

Рабочий контур:

```text
Baseline CI success on main
  → Deploy Stage workflow
  → self-hosted runner /home/ubuntu/actions-runner-site-auditor
  → exact commit checkout
  → transactional app-source switch
  → docker compose build/up
  → health + MCP smoke
  → rollback on failure
  → deployment evidence artifact
```

Подтверждено:

- deployment запускается после успешного CI для `main`;
- разворачивается полный commit SHA;
- bundle формируется во временном каталоге и валидируется;
- предыдущий `app-source` сохраняется;
- переключение выполняется атомарно;
- Docker service пересобирается и пересоздаётся;
- ожидается состояние `healthy`;
- smoke проверяет `/api/health`, относительный `/mcp → /mcp/` и MCP initialize;
- при ошибке выполняется rollback;
- SHA и evidence сохраняются;
- ручное восстановление задокументировано;
- rollback-транзакция проверена воспроизводимым тестом с искусственно сорванным smoke: предыдущий bundle и SHA восстанавливаются, неуспешный bundle сохраняется в `app-source.failed.*`.

## SA-02.2 — активный следующий слой

```text
AIMETON control
  → OpenStack API immers.cloud
  → Keystone / Nova / Neutron / Cinder / Glance
  → VM, network, volumes, snapshots, recovery
```

OpenStack API не заменяет выполнение команд внутри Ubuntu. Внутренний deployment-контур SA-02.1 остаётся отдельным и завершённым.

## Оперативное управление

Состояние синхронизируется через `CURRENT_STATUS.md`, GitHub Issues, Pull Requests, Actions runs, deployment evidence и stage smoke results.
