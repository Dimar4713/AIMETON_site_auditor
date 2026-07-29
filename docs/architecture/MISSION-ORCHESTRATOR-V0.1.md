# AIMETON Mission Orchestrator v0.1

Статус: code baseline `SA-SR-02 / #83` слит PR `#92` в `main`, merge SHA
`7b6602c98e02a982716112b34d225e66cebc4dad`; pre-merge Baseline CI
`#30470034095` — success. Эксплуатационный факт stage подтверждается отдельно
exact deployment SHA и live `/api/health`.

## Назначение

Mission Orchestrator создаёт один эквивалентный Mission Contract для UI, REST,
MCP и backward-compatible `/api/analyze`, управляет допустимыми действиями и
сохраняет trace оборотов:

```text
plan → acquire → analyze → resolve → evaluate → replan / stop
```

Orchestrator не подменяет crawler, Entity Resolution или УДП Evaluator. Он
задаёт их исполнимые порты:

- `ActionCandidate` от AI/crawler/entity/evaluator;
- `PolicySnapshot` от детерминированной политики;
- `NextActionPlan` на исполнение;
- `ActionOutcome` от capability;
- `SufficiencyFeedback` от будущего `#86`;
- `TurnTrace` как связь before/action/artifacts/after.

## Mission Contract

До первого действия обязательны:

- уникальные `mission_id`, `analysis_id`, `correlation_id`;
- target URL и цель;
- целевой УДП;
- обязательные/критические вопросы и freshness;
- deadline, action budget и бюджеты по валютам;
- семантический `contract_fingerprint`.

`contract_fingerprint` не включает entry point и случайные ID. Поэтому
одинаковый запрос через UI, REST и MCP даёт эквивалентный контракт, но
изолированные mission/analysis/correlation IDs.

## NextActionPlan

Поддерживаемые action types:

- `crawl_url`;
- `fetch_document`;
- `query_provider`;
- `resolve_identity`;
- `review_conflict`;
- `stop`.

AI может задать `ai_priority`, ожидаемый прирост УДП, cost, latency и risk.
Выбор остаётся воспроизводимым: сначала Policy Guard удаляет недопустимые
действия, затем сортировка выбирает максимальный ожидаемый прирост с
детерминированными tie-breakers. Порядок candidates во входе не меняет
решение или порядок `decisions`; идентичный повтор plan идемпотентен, а
конкурирующая замена pending plan того же оборота отклоняется.

## Policy Guard

До исполнения проверяются:

- разрешённый action type;
- action/deadline budget как пересечение Mission Contract и текущей policy;
- накопленный фактический расход и budget по каждой валюте;
- robots;
- SSRF validation;
- права;
- domain allowlist;
- rate limit.

Если допустимых действий нет, создаётся `stop` с
`policy_no_admissible_action`. AI не может ослабить policy flags или открыть
Report Gate. Outcome принимается только для последнего `NextActionPlan`,
выданного этим экземпляром orchestrator; подмена сериализованного плана
отклоняется. Отрицательные денежные значения запрещены, а расход в
незапланированной валюте или сверх Mission Contract переводит миссию в
`blocked / budget_exhausted`, не удаляя trace фактического вызова.
Для `crawl_url` и `fetch_document` пустой domain allowlist закрывает действие.

## Lifecycle и запрет ложного завершения

Состояния:

```text
planned → running ↔ degraded → blocked | completed
```

`sufficiency_reached` разрешает `completed` только если:

1. achieved УДП не ниже target;
2. ни один обязательный вопрос не остался `not_searched`.

Иначе миссия получает `blocked / invalid_completion`.

Частичный или неуспешный оборот не удаляет ранее собранные `artifact_refs`.
Другая mission не может прочитать эти artifacts или turns.

## Адаптеры

- `POST /api/missions` — создать каноническую REST mission;
- `GET /api/missions/{mission_id}` — получить snapshot;
- `POST /api/missions/{mission_id}/plan` — применить Policy Guard;
- `POST /api/missions/{mission_id}/turns` — записать outcome и feedback;
- MCP `start_search_mission` использует тот же builder;
- `/api/analyze` и MCP `analyze_site` являются legacy adapters: они сначала
  создают mission и записывают preliminary turn, а не формируют невидимый
  второй контур.

## Граница v0.1

Turn trace хранится process-local. Устойчивые checkpoints, restart recovery и
распределённая блокировка относятся к `#88`. Bootstrap/targeted acquisition
реализует `#85`, identity feedback — `#84`, канонический пересчёт УДП — `#86`.
До этих интеграций legacy turn остаётся `L0` и не может завершить миссию или
разрешить клиентский выпуск.
