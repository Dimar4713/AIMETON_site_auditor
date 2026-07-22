# AIMETON Runtime Core v0.1

## Назначение и bounded context

Runtime Core хранит переносимое состояние исполнения AIMETON. Он знает о задаче, субъекте действия, мандате, обязательстве, событиях, доказательствах, шагах плана и запусках инструментов, но не знает бизнес-логику Site Auditor, отраслевые справочники, поисковые стратегии или правила формирования коммерческого предложения.

Граница ответственности:

```text
GitHub Issue / Project ── external reference ──► Runtime Task
                                                   │
                                                   ├─ actor + mandate
                                                   ├─ commitment + completion criteria
                                                   ├─ events + plan steps
                                                   ├─ evidence
                                                   └─ tool execution records
                                                            ▲
                                                            │ adapter
                                                   Site Auditor / другой tool
```

GitHub остаётся системой управления разработкой. Runtime Task остаётся состоянием исполнения. Они связываются через `external_refs`, но не подменяют друг друга.

## Канонические сущности

- `Task` — обязательство выполнить ограниченную работу и её lifecycle state;
- `Actor reference` — ссылка на действующего субъекта или системный орган;
- `Mandate reference` — ссылка на границы разрешённых полномочий;
- `Commitment` — обещанный результат;
- `Completion criteria` — проверяемые признаки завершения;
- `Event` — факт изменения состояния или значимое наблюдение;
- `Evidence` — санитарно очищенное основание результата;
- `ToolExecution` — запись вызова инструмента и статуса результата;
- `PlanStep` — отдельный шаг плана;
- `Correlation ID` — сквозная связь записей одного исполнения.

Каждая write-запись обязана содержать `task_id`, `actor_ref`, `mandate_ref`, `reason` и `correlation_id`.

## Lifecycle v0.1

```text
created → planned → in_progress → validation → completed
                       │              │
                       ├─ blocked ────┘
                       ├─ failed
                       └─ cancelled
```

Runtime Core v0.1 сохраняет переход как событие. Политика допустимых переходов будет усилена в следующем инкременте; сейчас ядро фиксирует трассировку, не навязывая прикладному инструменту его workflow.

## Хранилище и миграции

Базовое постоянное хранилище — SQLite:

```text
AIMETON_RUNTIME_DB=data/runtime-core.sqlite3
```

Причины выбора для v0.1:

- состояние переживает restart/redeploy;
- не требуется отдельная инфраструктура;
- транзакционность и WAL доступны из стандартной библиотеки Python;
- Store contract можно позднее реализовать для PostgreSQL без изменения канонических моделей и адаптеров.

Текущая схема имеет `schema_version=1` в таблице `runtime_meta`. Все последующие изменения выполняются только возрастающими миграциями; destructive migration без экспортируемого backup запрещена.

Каталог `data/` должен быть постоянным volume и не должен входить в Git.

## Отдельный запуск Runtime Core

```bash
AIMETON_RUNTIME_DB=/var/lib/aimeton/runtime.sqlite3 \
uvicorn app.runtime_core.service:app --host 0.0.0.0 --port 5100
```

Health:

```http
GET /health
GET /api/runtime/health
```

Site Auditor может также подключить тот же router внутрь своего процесса. Это режим совместного deployment для текущего stage, а не архитектурное смешение bounded contexts.

## Runtime API

```text
POST /api/runtime/tasks
GET  /api/runtime/tasks
GET  /api/runtime/tasks/{task_id}
POST /api/runtime/tasks/{task_id}/transition
POST /api/runtime/tasks/{task_id}/events
POST /api/runtime/tasks/{task_id}/evidence
POST /api/runtime/tasks/{task_id}/tool-executions
POST /api/runtime/tasks/{task_id}/plan-steps
GET  /api/runtime/tasks/{task_id}/records
```

Пример регистрации задачи:

```json
{
  "title": "Анализ компании",
  "actor_ref": "aimeton.actor.site-auditor",
  "mandate_ref": "aimeton.mandate.economic-intelligence.read-only",
  "commitment": "Сформировать доказательный профиль компании",
  "completion_criteria": [
    "приложено evidence",
    "зарегистрирован tool execution"
  ],
  "external_refs": {
    "github_issue": "40"
  },
  "correlation_id": "corr_example"
}
```

## Site Auditor adapter

`app/site_auditor_runtime_adapter.py` является тонким анти-коррупционным слоем. Он:

1. создаёт Runtime Task от имени Site Auditor;
2. фиксирует принятие задачи;
3. прикладывает санитарно очищенное evidence;
4. регистрирует tool execution;
5. переводит задачу в completed после выполнения критериев.

Адаптер не переносит в Runtime Core парсинг сайтов, OSINT, LLM, KM-профиль или коммерческую квалификацию. Другой инструмент может заменить Site Auditor, реализовав тот же порядок записи.

## Безопасность audit trail

Запрещено сохранять в Runtime Core:

- API keys, Bearer tokens и cookies;
- полный process environment;
- raw prompts и внутренние chain-of-thought данные;
- необработанные персональные данные без отдельного мандата;
- содержимое закрытых документов, когда достаточно ссылки и digest.

В evidence сохраняются источник/ссылка, краткое санитарно очищенное резюме и опциональный digest. Большие или чувствительные артефакты должны храниться во внешнем защищённом evidence store.

## Проверяемый end-to-end сценарий

Автоматический тест подтверждает:

```text
создание task
→ переход in_progress
→ запись evidence
→ запись tool execution со ссылкой на evidence
→ переход completed
→ повторное открытие SQLite и восстановление состояния
```

## Следующие инкременты

- строгая матрица допустимых lifecycle transitions;
- idempotency keys для write API;
- PostgreSQL store и миграционный runner;
- отдельная auth boundary Runtime Core;
- evidence object store;
- webhook/worker для связи GitHub lifecycle с external refs;
- выделение Runtime Core в отдельный репозиторий после стабилизации контракта v0.1.
