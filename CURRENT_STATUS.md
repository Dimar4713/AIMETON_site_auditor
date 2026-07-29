# AIMETON Site Auditor · Current Status

_Last updated: 2026-07-29_

## Активный контур Search Recovery

- `SR-G0 / #81` слит в `main` через PR
  [#79](https://github.com/Dimar4713/AIMETON_site_auditor/pull/79);
  merge SHA `1f3f2d6bbe9fc350dffcb58accd539ccf70f1a8e`.
- `MissionReleaseControl` и fail-closed Report Gate являются фактом `main`, но
  не доказывают восстановление самого поиска.
- `SR-G1 / #82` слит через PR
  [#91](https://github.com/Dimar4713/AIMETON_site_auditor/pull/91) и
  развёрнут на stage: версия `0.12.0`, deployment SHA
  `5b6a65d0d26b64087b0e90d3f040668c7d7cdfce`.
- Live provider readiness: SearXNG — `active`, `ready=true`; Yandex и Tavily —
  `not_configured`, `ready=false`; `secrets_exposed=false`.
- Кодировки, полнота смысловых областей, URL/redirect/canonical identity и
  operational readiness providers являются фактом `main` и stage.
- Регистрационные данные платных providers потребуются только после зелёного
  CI `#82`, перед live-проверкой stage. Значения секретов не передаются через
  чат, Issues, PR, код или логи.

## Текущее положение

Ниже сохранён исторический эксплуатационный baseline SA-01/SA-02. Он не
заменяет активный контур Search Recovery выше.

**Исторически завершённая фаза:** SA-01 — стабилизация поискового и MCP-контура.

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
- rollback-транзакция проверена воспроизводимым тестом с искусственно сорванным smoke: предыдущий bundle и SHA восстанавливаются, неуспешный bundle сохраняется в `app-source.failed.*`;
- rollback evidence закреплён тестом `tests/test_deploy_stage_rollback.py`, итоговый commit `233e39bf0b4aa6266526d847e7fcbbd832505792`.

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
